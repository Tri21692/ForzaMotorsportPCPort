/* The Xbox file system on host directories.
 *
 * Xbox paths are object names such as \??\D:\media\cars.dat. Drive
 * letters are symbolic links the game creates (\??\D: -> \Device\CdRom0),
 * and devices map to host directories:
 *   \Device\CdRom0                 XBRT_DISC, default the XBE's directory
 *   \Device\Harddisk0\PartitionN   XBRT_HDD/PartitionN, default ./hdd
 * Names match case-insensitively, as on the Xbox's FATX and disc file
 * systems.
 */
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <unistd.h>

#include "rt.h"

#ifdef _WIN32
#include <io.h>
#include <windows.h>
/* MinGW has no pread/pwrite. ReadFile with an offset is one, and it
 * leaves the descriptor's own position alone, as pread does. */
static ssize_t pread(int fd, void *buf, size_t n, off_t pos) {
    OVERLAPPED ov = {0};
    ov.Offset = (DWORD)pos, ov.OffsetHigh = (DWORD)((uint64_t)pos >> 32);
    DWORD got = 0;
    if (!ReadFile((HANDLE)_get_osfhandle(fd), buf, (DWORD)n, &got, &ov))
        return GetLastError() == ERROR_HANDLE_EOF ? 0 : -1;
    return got;
}
static ssize_t pwrite(int fd, const void *buf, size_t n, off_t pos) {
    OVERLAPPED ov = {0};
    ov.Offset = (DWORD)pos, ov.OffsetHigh = (DWORD)((uint64_t)pos >> 32);
    DWORD put = 0;
    if (!WriteFile((HANDLE)_get_osfhandle(fd), buf, (DWORD)n, &put, &ov)) return -1;
    return put;
}
#define mkdir(path, mode) mkdir(path)
#else
#define O_BINARY 0
#endif

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))

typedef struct {
    char link[64], target[128];
} Symlink;
static Symlink links[32];
static int nlinks;
static char disc_dir[1024], hdd_dir[1024];

void rt_files_init(void) {
    const char *d = getenv("XBRT_DISC"), *h = getenv("XBRT_HDD");
    snprintf(disc_dir, sizeof disc_dir, "%s", d ? d : rt_image.dir);
    snprintf(hdd_dir, sizeof hdd_dir, "%s", h ? h : "hdd");
    rt_log("disc: %s, hard disk: %s\n", disc_dir, hdd_dir);
}

uint32_t rt_symlink(const char *link, const char *target) {
    for (int i = 0; i < nlinks; i++) {
        if (!strcasecmp(links[i].link, link)) {
            snprintf(links[i].target, sizeof links[i].target, "%s", target);
            return STATUS_SUCCESS;
        }
    }
    if (nlinks == 32) return STATUS_NO_MEMORY;
    snprintf(links[nlinks].link, sizeof links[nlinks].link, "%s", link);
    snprintf(links[nlinks].target, sizeof links[nlinks].target, "%s", target);
    nlinks++;
    rt_log("  symlink %s -> %s\n", link, target);
    return STATUS_SUCCESS;
}

/* OBJECT_ATTRIBUTES: RootDirectory, ObjectName (STRING *), Attributes. */
const char *rt_object_name(uint32_t oa, char *out, size_t n) {
    uint32_t root = xb_rd32(oa), name = xb_rd32(oa + 4);
    char rel[512] = "";
    if (name) snprintf(rel, sizeof rel, "%.*s", xb_rd16(name), rt_str(xb_rd32(name + 4)));
    RtObject *r = root ? rt_handle_get(root) : NULL;
    if (r && r->path) snprintf(out, n, "%s%s%s", r->path, rel[0] && rel[0] != '\\' ? "\\" : "", rel);
    else snprintf(out, n, "%s", rel);
    return out;
}

/* Rewrite an Xbox object path to start at a device: follow \??\X: and
 * bare X: through the symbolic links. */
static void resolve_links(const char *in, char *out, size_t n) {
    char buf[600];
    const char *p = in;
    if (!strncmp(p, "\\??\\", 4)) p += 4;
    if (p[0] && p[1] == ':') {
        char drive[8];
        snprintf(drive, sizeof drive, "\\??\\%c:", p[0]);
        for (int i = 0; i < nlinks; i++) {
            if (!strcasecmp(links[i].link, drive)) {
                snprintf(buf, sizeof buf, "%s%s", links[i].target, p + 2);
                snprintf(out, n, "%s", buf);
                return;
            }
        }
    }
    snprintf(out, n, "%s", in);
}

/* root, then rest's components matched case-insensitively one directory at
 * a time; a missing one is kept as written. Returns 0 if any was missing. */
static int walk(const char *root, const char *rest, char *out, size_t n) {
    int found = 1;
    snprintf(out, n, "%s", root);
    char comp[256];
    while (*rest) {
        while (*rest == '\\') rest++;
        if (!*rest) break;
        size_t k = 0;
        while (rest[k] && rest[k] != '\\' && k < sizeof comp - 1) comp[k] = rest[k], k++;
        comp[k] = 0;
        rest += k;
        if (!strcmp(comp, ".")) continue;
        DIR *d = opendir(out);
        const char *match = NULL;
        struct dirent *e;
        while (d && (e = readdir(d))) {
            if (!strcasecmp(e->d_name, comp)) {
                match = e->d_name;
                break;
            }
        }
        if (!match) match = comp, found = 0;
        size_t len = strlen(out);
        snprintf(out + len, n - len, "/%s", match);
        if (d) closedir(d);
    }
    return found;
}

/* The mods folder (forza.ini: mods): a file there, at the same path as on
 * the disc (mods/media/cabs/car_nissan240sx.cab), is read instead of the
 * disc's. Files only; directories are still listed from the disc. */
static int mods_off;   /* set while an open that writes looks a path up: those go to the real file */
static int from_mods;  /* the last host_path came from the mods folder */
static int mod_file(const char *rest, char *out, size_t n) {
    static char dir[1024];
    static int checked;
    if (!checked) {
        checked = 1;
        const char *m = getenv("XBRT_MODS");
        snprintf(dir, sizeof dir, "%s", m ? m : "");
        if (dir[0]) mkdir(dir, 0755); /* there to be found and filled */
        struct stat st;
        if (dir[0] && stat(dir, &st) == 0 && S_ISDIR(st.st_mode)) rt_log("mods: %s\n", dir);
        else dir[0] = 0;
    }
    if (!dir[0] || mods_off) return 0;
    char path[1200];
    struct stat st;
    if (!walk(dir, rest, path, sizeof path) || stat(path, &st) != 0 || !S_ISREG(st.st_mode)) return 0;
    snprintf(out, n, "%s", path);
    from_mods = 1;
    return 1;
}

/* Find a host path for a device-relative name, matching each component
 * case-insensitively. Missing trailing components are kept as written,
 * so creating a new file works. */
static int host_path(const char *xbox, char *out, size_t n) {
    from_mods = 0;
    char dev[600];
    resolve_links(xbox, dev, sizeof dev);
    const char *rest;
    char root[1100];
    if (!strncasecmp(dev, "\\Device\\CdRom0", 14)) {
        snprintf(root, sizeof root, "%s", disc_dir);
        rest = dev + 14;
        if (mod_file(rest, out, n)) {
            static int said;
            if (said < 100) said++, fprintf(stderr, "xbrt: mods: %s\n", out);
            return 1;
        }
    } else if (!strncasecmp(dev, "\\Device\\Harddisk0\\Partition", 27)) {
        int part = atoi(dev + 27);
        snprintf(root, sizeof root, "%s/Partition%d", hdd_dir, part);
        mkdir(hdd_dir, 0755);
        mkdir(root, 0755);
        rest = dev + 27;
        while (*rest >= '0' && *rest <= '9') rest++;
        /* The cache partitions too (mods/hdd/Partition4/mega.cab): the archives
         * the game installed there from the disc (wheels are in mega.cab and
         * megaxpr.cab). Not saves: partitions 1 and 2 are left alone. */
        char modrest[700];
        snprintf(modrest, sizeof modrest, "\\hdd\\Partition%d%s", part, rest);
        if (part >= 3 && mod_file(modrest, out, n)) {
            static int said;
            if (said < 100) said++, fprintf(stderr, "xbrt: mods: %s\n", out);
            return 1;
        }
    } else {
        return 0;
    }
    walk(root, rest, out, n);
    return 1;
}

/* \Device\Harddisk0\PartitionN with nothing after it is the raw volume,
 * not its root directory. XAPI reads and writes partition 0 directly (the
 * cache partition table) and formats cache partitions through their raw
 * volumes. Partition 0 is backed by a file; reads past its end, and raw
 * reads of other partitions, give zeros, as from a blank disk. Raw writes
 * to other partitions (a FATX format) are accepted and dropped: their
 * files live in the host folder. Returns the partition number, or -1. */
static int raw_partition(const char *xbox) {
    char dev[600];
    resolve_links(xbox, dev, sizeof dev);
    if (strncasecmp(dev, "\\Device\\Harddisk0\\Partition", 27)) return -1;
    const char *p = dev + 27;
    if (*p < '0' || *p > '9') return -1;
    int n = 0;
    while (*p >= '0' && *p <= '9') n = n * 10 + (*p++ - '0');
    return *p ? -1 : n;
}

static uint32_t open_raw(uint32_t *handle, const char *xbox, int part, uint32_t *info) {
    uint32_t h = rt_handle_new(OBJ_FILE);
    RtObject *o = rt_handle_get(h);
    o->raw = part + 1;
    o->path = strdup(xbox);
    if (part == 0) {
        char host[1100];
        mkdir(hdd_dir, 0755);
        snprintf(host, sizeof host, "%s/partition0.bin", hdd_dir);
        o->fd = open(host, O_RDWR | O_CREAT | O_BINARY, 0644);
    }
    *handle = h;
    *info = 1;
    rt_log("  open %s: raw partition %d, handle %x\n", xbox, part, h);
    return STATUS_SUCCESS;
}

/* Share access, as the NT I/O manager checks it. Each open file uses some
 * of read, write and delete (from its desired access) and lets other
 * opens use some (its share access). A new open fails with a sharing
 * violation if it wants what an open file does not share, or does not
 * share what an open file uses. Forza relies on this: its installer
 * reopens an archive it is still writing with CREATE_ALWAYS and no
 * sharing, expecting that to fail rather than truncate the file. */
#define SHARE_READ 1u
#define SHARE_WRITE 2u
#define SHARE_DELETE 4u
#define STATUS_SHARING_VIOLATION 0xC0000043u

static uint8_t access_bits(uint32_t desired) {
    uint8_t a = 0;
    if (desired & (0x80000000u | 0x10000000u | 0x0001u | 0x0020u)) a |= SHARE_READ;  /* GENERIC_READ/ALL, READ_DATA, EXECUTE */
    if (desired & (0x40000000u | 0x10000000u | 0x0002u | 0x0004u)) a |= SHARE_WRITE; /* GENERIC_WRITE/ALL, WRITE/APPEND_DATA */
    if (desired & (0x00010000u | 0x10000000u)) a |= SHARE_DELETE;                    /* DELETE */
    return a;
}

static int share_conflict(const char *host, uint8_t access, uint8_t share) {
    if (!access) return 0; /* attribute-only opens never conflict */
    for (int i = 1; i < 4096; i++) {
        RtObject *o = rt_handle_slot(i);
        if (!o || o->type != OBJ_FILE || !o->host || !o->access || strcasecmp(o->host, host)) continue;
        if ((access & ~o->share) || (o->access & ~share)) return 1;
    }
    return 0;
}

uint32_t rt_open(uint32_t *handle, uint32_t oa, uint32_t desired, uint32_t share, uint32_t disposition,
                 uint32_t options, uint32_t *info) {
    char xbox[600], host[1200];
    rt_object_name(oa, xbox, sizeof xbox);
    const char *trace = getenv("XBRT_TRACE_OPEN"); /* debugging: who opens this file? */
    if (trace && *trace && strstr(xbox, trace)) {
        fprintf(stderr, "xbrt: open %s (disposition %u)\n", xbox, disposition);
        rt_backtrace(rt_self ? &rt_self->ctx : NULL);
    }
    int part = raw_partition(xbox);
    if (part >= 0) return open_raw(handle, xbox, part, info);
    if (!host_path(xbox, host, sizeof host)) {
        rt_log("  open %s: no such device\n", xbox);
        return STATUS_OBJECT_PATH_NOT_FOUND;
    }
    /* Mods are read: an open that writes or truncates (the game reinstalling
     * its cache, say) gets the real file, not the mod. */
    if (from_mods && ((access_bits(desired) & (SHARE_WRITE | SHARE_DELETE)) || disposition == 0 || disposition == 4 || disposition == 5)) {
        mods_off = 1;
        host_path(xbox, host, sizeof host);
        mods_off = 0;
    }
    int read_only = from_mods;
    struct stat st;
    int exists = stat(host, &st) == 0;
    int is_dir = exists && S_ISDIR(st.st_mode);
    if ((options & 0x40) && is_dir) return STATUS_ACCESS_DENIED; /* FILE_NON_DIRECTORY_FILE */
    int flags = O_RDWR | O_BINARY;
    switch (disposition) {
    case 0: case 5: flags |= O_CREAT | O_TRUNC; break; /* SUPERSEDE, OVERWRITE_IF */
    case 1: if (!exists) goto missing; break;          /* OPEN */
    case 2: if (exists) return STATUS_OBJECT_NAME_COLLISION; flags |= O_CREAT; break;
    case 3: flags |= O_CREAT; break;                   /* OPEN_IF */
    case 4: if (!exists) goto missing; flags |= O_TRUNC; break;
    }
    uint8_t access = access_bits(desired);
    if (exists && !is_dir && share_conflict(host, access, (uint8_t)(share & 7))) {
        fprintf(stderr, "xbrt: open %s: sharing violation (access %x, share %x)\n", xbox, access, share & 7);
        return STATUS_SHARING_VIOLATION;
    }
    uint32_t h;
    if (is_dir || ((options & 0x1) && !exists)) { /* FILE_DIRECTORY_FILE */
        if (!exists && mkdir(host, 0755) != 0) return STATUS_OBJECT_PATH_NOT_FOUND;
        h = rt_handle_new(OBJ_DIR);
    } else {
        int fd = read_only ? open(host, O_RDONLY | O_BINARY) : open(host, flags, 0644);
        if (fd < 0 && (errno == EACCES || errno == EROFS)) fd = open(host, O_RDONLY | O_BINARY); /* a read-only disc copy */
        if (fd < 0) goto missing;
        h = rt_handle_new(OBJ_FILE);
        RtObject *f = rt_handle_get(h);
        f->fd = fd;
        f->host = strdup(host);
        f->access = access;
        f->share = (uint8_t)(share & 7);
        f->unbuffered = (options & 0x8) != 0;
    }
    RtObject *o = rt_handle_get(h);
    o->path = strdup(xbox);
    *handle = h;
    *info = exists ? 1 : 2; /* FILE_OPENED / FILE_CREATED */
    rt_log("  open %s -> %s: handle %x\n", xbox, host, h);
    return STATUS_SUCCESS;
missing:
    rt_log("  open %s -> %s: not found\n", xbox, host);
    return STATUS_OBJECT_NAME_NOT_FOUND;
}

static void io_status(uint32_t iosb, uint32_t status, uint32_t info) {
    if (!iosb) return;
    xb_wr32(iosb, status);
    xb_wr32(iosb + 4, info);
}

/* NtCreateFile(FileHandle*, DesiredAccess, ObjectAttributes*, IoStatusBlock*,
 *              AllocationSize*, FileAttributes, ShareAccess, CreateDisposition, CreateOptions) */
uint32_t k_file_NtCreateFile(XbCtx *c) {
    uint32_t h = 0, info = 0;
    uint32_t r = rt_open(&h, ARG(2), ARG(1), ARG(6), ARG(7), ARG(8), &info);
    if (r == STATUS_SUCCESS) xb_wr32(ARG(0), h);
    io_status(ARG(3), r, info);
    return r;
}

/* NtOpenFile(FileHandle*, DesiredAccess, ObjectAttributes*, IoStatusBlock*, ShareAccess, OpenOptions) */
uint32_t k_file_NtOpenFile(XbCtx *c) {
    uint32_t h = 0, info = 0;
    uint32_t r = rt_open(&h, ARG(2), ARG(1), ARG(4), 1, ARG(5), &info);
    if (r == STATUS_SUCCESS) xb_wr32(ARG(0), h);
    io_status(ARG(3), r, info);
    return r;
}

/* NtReadFile(FileHandle, Event, ApcRoutine, ApcContext, IoStatusBlock*, Buffer, Length, ByteOffset*) */
uint32_t k_file_NtReadFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_FILE) {
        fprintf(stderr, "xbrt: NtReadFile on handle %x, which is %s (from %08x)\n", ARG(0), o ? "not a file" : "not open",
                xb_rd32(c->esp));
        return STATUS_INVALID_HANDLE;
    }
    uint64_t pos = ARG(7) ? xb_rd64(ARG(7)) : o->pos;
    rt_mem_commit(ARG(5), ARG(6)); /* the host writes this memory, not guest code */
    ssize_t n = o->fd >= 0 ? pread(o->fd, xb_mem + ARG(5), ARG(6), (off_t)pos) : 0;
    if (n < 0) n = 0;
    if (o->raw && (uint32_t)n < ARG(6)) { /* a blank disk past what was written */
        memset(xb_mem + ARG(5) + n, 0, ARG(6) - (uint32_t)n);
        n = ARG(6);
    }
    o->pos = pos + (uint64_t)n;
    static int file_log = -1; /* debugging: XBRT_FILE_LOG=1 logs every read, without the rest of XBRT_LOG=2 */
    if (file_log < 0) file_log = getenv("XBRT_FILE_LOG") && atoi(getenv("XBRT_FILE_LOG"));
    if (file_log)
        fprintf(stderr, "xbrt: [%.3f] read %s (%s) at %llx: %lld bytes\n", rt_now_100ns() / 1e7, o->path ? o->path : "?",
                o->host ? o->host : "", (unsigned long long)pos, (long long)n);
    if (rt_log_level >= 2)
        rt_log("  read %s at %llx: %lld bytes, %08x %08x\n", o->path ? o->path : "?", (unsigned long long)pos,
               (long long)n, n >= 4 ? xb_rd32(ARG(5)) : 0, n >= 8 ? xb_rd32(ARG(5) + 4) : 0);
    /* Reading at or past the end fails at once. A request that fails
     * before it is queued leaves the caller's IO_STATUS_BLOCK, event and
     * APC alone, as the NT I/O manager does; Forza reads ahead past the
     * end of its files and would otherwise collect a result for a read
     * that never started. */
    if (n == 0 && ARG(6)) {
        static int warned;
        if (warned++ < 20)
            fprintf(stderr, "xbrt: read past the end of %s at %llx (%u bytes, %s)\n", o->path ? o->path : "?",
                    (unsigned long long)pos, ARG(6), ARG(1) || ARG(2) ? "with an event or APC" : "synchronous");
        return STATUS_END_OF_FILE;
    }
    uint32_t r = STATUS_SUCCESS;
    io_status(ARG(4), r, (uint32_t)n);
    if (ARG(1)) {
        RtObject *e = rt_handle_get(ARG(1));
        if (e) e->signaled = 1;
        pthread_cond_broadcast(&rt_changed);
    }
    if (ARG(2)) rt_queue_user_apc(ARG(2), ARG(3), ARG(4));
    return r;
}

uint32_t k_file_NtWriteFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_FILE) return STATUS_INVALID_HANDLE;
    uint64_t pos = ARG(7) ? xb_rd64(ARG(7)) : o->pos;
    uint32_t len = ARG(6);
    /* Unbuffered writes come in whole sectors, so the last one of a file
     * runs past its end. FATX drops that tail rather than growing the
     * file: Forza's installer sizes each file first, copies it in 128 KB
     * blocks and then checks the size is still exact. A write that starts
     * at or past the end still extends the file. */
    struct stat st;
    if (o->unbuffered && o->fd >= 0 && fstat(o->fd, &st) == 0 && pos < (uint64_t)st.st_size &&
        pos + len > (uint64_t)st.st_size)
        len = (uint32_t)((uint64_t)st.st_size - pos);
    ssize_t n = o->fd >= 0 ? pwrite(o->fd, xb_mem + ARG(5), len, (off_t)pos) : (ssize_t)len;
    if (n < 0) return STATUS_ACCESS_DENIED;
    if ((uint32_t)n == len) n = ARG(6); /* the clipped tail counts as written */
    if (rt_log_level >= 2)
        rt_log("  write %s at %llx: %lld bytes, %08x %08x\n", o->path ? o->path : "?", (unsigned long long)pos,
               (long long)n, n >= 4 ? xb_rd32(ARG(5)) : 0, n >= 8 ? xb_rd32(ARG(5) + 4) : 0);
    o->pos = pos + (uint64_t)n;
    io_status(ARG(4), STATUS_SUCCESS, (uint32_t)n);
    if (ARG(1)) {
        RtObject *e = rt_handle_get(ARG(1));
        if (e) e->signaled = 1;
        pthread_cond_broadcast(&rt_changed);
    }
    if (ARG(2)) rt_queue_user_apc(ARG(2), ARG(3), ARG(4));
    return STATUS_SUCCESS;
}

/* NtFlushBuffersFile(FileHandle, IoStatusBlock*): XAPI's FlushFileBuffers,
 * which saves call before closing. Writes already reach the host file
 * system, which keeps them across a crash of this process. */
uint32_t k_file_NtFlushBuffersFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_FILE) return STATUS_INVALID_HANDLE;
    io_status(ARG(1), STATUS_SUCCESS, 0);
    return STATUS_SUCCESS;
}

/* NtFsControlFile(FileHandle, Event, ApcRoutine, ApcContext, IoStatusBlock*,
 *                 FsControlCode, InputBuffer, InputLength, OutputBuffer, OutputLength)
 * XAPI dismounts and locks a cache partition before formatting it. Host
 * folders need neither, so every request succeeds with no output. */
uint32_t k_file_NtFsControlFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    rt_log("  fs control %08x on %s\n", ARG(5), o->path ? o->path : "?");
    io_status(ARG(4), STATUS_SUCCESS, 0);
    return STATUS_SUCCESS;
}

/* The size of a raw partition, as the retail hard disk lays them out:
 * partitions 3-5 are the 750 MB cache partitions. */
static uint64_t partition_bytes(int part) {
    switch (part) {
    case 1: return 4882ull << 20;  /* E: */
    case 2: return 500ull << 20;   /* C: */
    case 3: case 4: case 5: return 750ull << 20;
    }
    return 8ull << 30;
}

/* NtDeviceIoControlFile(FileHandle, Event, ApcRoutine, ApcContext, IoStatusBlock*,
 *                       IoControlCode, InputBuffer, InputLength, OutputBuffer, OutputLength) */
uint32_t k_file_NtDeviceIoControlFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    uint32_t code = ARG(5), out = ARG(8), outlen = ARG(9);
    uint64_t bytes = partition_bytes(o->raw - 1);
    switch (code) {
    case 0x00070000: /* IOCTL_DISK_GET_DRIVE_GEOMETRY: one sector per track, so cylinders = sectors */
        if (outlen < 24) return 0xC0000023u; /* STATUS_BUFFER_TOO_SMALL */
        xb_wr64(out, bytes / 512);
        xb_wr32(out + 8, 12); /* FixedMedia */
        xb_wr32(out + 12, 1);
        xb_wr32(out + 16, 1);
        xb_wr32(out + 20, 512);
        io_status(ARG(4), STATUS_SUCCESS, 24);
        return STATUS_SUCCESS;
    case 0x00074004: /* IOCTL_DISK_GET_PARTITION_INFO */
        if (outlen < 32) return 0xC0000023u;
        memset(xb_mem + out, 0, 32);
        xb_wr64(out, 0x80000ull + (uint64_t)(o->raw - 1) * (1ull << 30)); /* StartingOffset */
        xb_wr64(out + 8, bytes);                                          /* PartitionLength */
        xb_wr32(out + 20, (uint32_t)(o->raw - 1));                        /* PartitionNumber */
        xb_wr8(out + 24, 0x0E);                                           /* PartitionType */
        xb_wr8(out + 26, 1);                                              /* RecognizedPartition */
        io_status(ARG(4), STATUS_SUCCESS, 32);
        return STATUS_SUCCESS;
    }
    rt_fatal(c, "NtDeviceIoControlFile: control code %08x on %s not implemented", code, o->path ? o->path : "?");
}

static void write_times_and_sizes(uint32_t out, uint64_t size, int dir) {
    for (int i = 0; i < 4; i++) xb_wr64(out + 8 * i, 0x01C4F00000000000ull); /* some date in 2005 */
    xb_wr64(out + 32, (size + 0xFFF) & ~0xFFFull);                          /* AllocationSize */
    xb_wr64(out + 40, size);                                                 /* EndOfFile */
    xb_wr32(out + 48, dir ? 0x10 : 0x80);                                    /* DIRECTORY / NORMAL */
}

/* NtQueryInformationFile(FileHandle, IoStatusBlock*, FileInformation, Length, FileInformationClass) */
uint32_t k_file_NtQueryInformationFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    uint32_t out = ARG(2), cls = ARG(4);
    struct stat st = {0};
    if (o->fd >= 0) fstat(o->fd, &st);
    int dir = o->type == OBJ_DIR;
    switch (cls) {
    case 5: /* FileStandardInformation */
        xb_wr64(out, ((uint64_t)st.st_size + 0xFFF) & ~0xFFFull);
        xb_wr64(out + 8, (uint64_t)st.st_size);
        xb_wr32(out + 16, 1);
        xb_wr8(out + 20, 0);
        xb_wr8(out + 21, dir);
        io_status(ARG(1), 0, 24);
        return STATUS_SUCCESS;
    case 14: /* FilePositionInformation */
        xb_wr64(out, o->pos);
        io_status(ARG(1), 0, 8);
        return STATUS_SUCCESS;
    case 34: /* FileNetworkOpenInformation */
        write_times_and_sizes(out, (uint64_t)st.st_size, dir);
        io_status(ARG(1), 0, 56);
        return STATUS_SUCCESS;
    }
    rt_fatal(c, "NtQueryInformationFile: class %u not implemented", cls);
}

/* NtSetInformationFile(FileHandle, IoStatusBlock*, FileInformation, Length, FileInformationClass) */
static uint32_t rename_file(RtObject *o, int replace, uint32_t root, uint32_t name);

uint32_t k_file_NtSetInformationFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o) return STATUS_INVALID_HANDLE;
    uint32_t in = ARG(2), cls = ARG(4);
    switch (cls) {
    case 14: /* FilePositionInformation */
        o->pos = xb_rd64(in);
        io_status(ARG(1), 0, 0);
        return STATUS_SUCCESS;
    case 19: case 20: /* FileAllocationInformation, FileEndOfFileInformation */
        if (o->fd >= 0 && ftruncate(o->fd, (off_t)xb_rd64(in)) != 0) return STATUS_ACCESS_DENIED;
        io_status(ARG(1), 0, 0);
        return STATUS_SUCCESS;
    case 4: /* FileBasicInformation: times and attributes, ignored */
        io_status(ARG(1), 0, 0);
        return STATUS_SUCCESS;
    case 13: /* FileDispositionInformation: BOOLEAN DeleteFile, done when the handle closes */
        o->delete_on_close = xb_rd8(in) != 0;
        io_status(ARG(1), 0, 0);
        return STATUS_SUCCESS;
    case 10: { /* FileRenameInformation: ReplaceIfExists, RootDirectory, OBJECT_STRING FileName */
        uint32_t r = rename_file(o, xb_rd8(in) != 0, xb_rd32(in + 4), in + 8);
        io_status(ARG(1), r, 0);
        return r;
    }
    }
    rt_fatal(c, "NtSetInformationFile: class %u not implemented", cls);
}

void rt_file_delete(const char *xbox) {
    char host[1200];
    mods_off = 1; /* never a mod: the game deletes its cache archives to install them again */
    int found = xbox && host_path(xbox, host, sizeof host);
    mods_off = 0;
    if (!found) return;
    int r = remove(host);
#ifdef _WIN32
    if (r != 0) r = rmdir(host); /* remove() does not take directories there */
#endif
    rt_log("  delete %s -> %s: %s\n", xbox, host, r == 0 ? "done" : "failed");
}

/* Rename an open file. Windows cannot rename a file that is open, so the
 * descriptor is closed around the rename and opened again after. */
static uint32_t rename_file(RtObject *o, int replace, uint32_t root, uint32_t name) {
    char rel[512], xbox[600], from[1200], to[1200];
    snprintf(rel, sizeof rel, "%.*s", xb_rd16(name), rt_str(xb_rd32(name + 4)));
    RtObject *r = root ? rt_handle_get(root) : NULL;
    if (r && r->path) snprintf(xbox, sizeof xbox, "%s\\%s", r->path, rel);
    else if (rel[0] != '\\' && !strchr(rel, ':') && o->path && strrchr(o->path, '\\'))
        snprintf(xbox, sizeof xbox, "%.*s%s", (int)(strrchr(o->path, '\\') - o->path + 1), o->path, rel);
    else snprintf(xbox, sizeof xbox, "%s", rel);
    mods_off = 1; /* never a mod (see rt_file_delete) */
    int found = o->path && host_path(o->path, from, sizeof from) && host_path(xbox, to, sizeof to);
    mods_off = 0;
    if (!found) return STATUS_OBJECT_PATH_NOT_FOUND;
    struct stat st;
    if (stat(to, &st) == 0) {
        if (!replace) return STATUS_OBJECT_NAME_COLLISION;
        remove(to);
    }
    if (o->fd >= 0) close(o->fd);
    int ok = rename(from, to) == 0;
    if (o->fd >= 0) o->fd = open(ok ? to : from, O_RDWR | O_BINARY);
    rt_log("  rename %s -> %s: %s\n", o->path, xbox, ok ? "done" : "failed");
    if (!ok) return STATUS_ACCESS_DENIED;
    free(o->path);
    o->path = strdup(xbox);
    return STATUS_SUCCESS;
}

/* NtQueryVolumeInformationFile(FileHandle, IoStatusBlock*, FsInformation, Length, FsInformationClass) */
static int on_disc(const RtObject *o) {
    char dev[600];
    resolve_links(o->path ? o->path : "", dev, sizeof dev);
    return !strncasecmp(dev, "\\Device\\CdRom0", 14);
}

/* FILE_OBJECT: Type (+0), DeviceObject (+4), FsContext (+8), FsContext2
 * (+0xC). FsContext points at the file system's FCB. XAPI reads it in
 * XGetFilePhysicalSortKey: on the disc (GDFX) the FCB starts with the
 * file's first sector, on FATX the first cluster is at +0x1C and bit 0 of
 * the first byte marks a directory. The runtime's FCB carries both, a
 * made-up sort key (files in the order they were first opened), and the
 * handle at +0x20 so a FILE_OBJECT leads back to the host file. */
uint32_t rt_file_object(uint32_t h) {
    static uint32_t next_key = 0x100;
    RtObject *o = rt_handle_get(h);
    if (!o || (o->type != OBJ_FILE && o->type != OBJ_DIR)) return 0;
    if (o->file_object) return o->file_object;
    uint32_t fo = rt_kdata_alloc(0x40), fcb = rt_kdata_alloc(0x30);
    xb_wr16(fo, 5); /* IO_TYPE_FILE */
    xb_wr32(fo + 8, fcb);
    uint32_t key = next_key++;
    xb_wr32(fcb, on_disc(o) ? key : (o->type == OBJ_DIR ? 1 : 0));
    xb_wr32(fcb + 0x1C, key);
    xb_wr32(fcb + 0x20, h);
    o->file_object = fo;
    return fo;
}

uint32_t rt_file_handle(uint32_t fo) {
    if (fo < RT_KDATA_BASE || fo >= RT_KDATA_LIMIT) return 0;
    uint32_t fcb = xb_rd32(fo + 8);
    return fcb >= RT_KDATA_BASE && fcb < RT_KDATA_LIMIT ? xb_rd32(fcb + 0x20) : 0;
}

/* Sectors per cluster on the volume a file is on. FATX uses 16 KB
 * clusters, except that a cache partition is formatted with the cluster
 * size the XBE asks for in bits 30-31 of its init flags (16-128 KB), and
 * XAPI checks for it before mounting the utility drive. */
static uint32_t cluster_sectors(const RtObject *o) {
    char dev[600];
    resolve_links(o && o->path ? o->path : "", dev, sizeof dev);
    if (!strncasecmp(dev, "\\Device\\Harddisk0\\Partition", 27)) {
        int part = atoi(dev + 27);
        if (part >= 3 && part <= 5) return 32u << (xb_rd32(rt_image.base + 0x124) >> 30);
    }
    return 32;
}

/* Volume information for the device a file is on; returns the bytes written. */
static uint32_t volume_info(XbCtx *c, RtObject *o, uint32_t cls, uint32_t out, uint32_t len) {
    uint32_t spc = cluster_sectors(o), clusters = (uint32_t)(0x40000ull * 32 / spc);
    switch (cls) {
    case 3: /* FileFsSizeInformation: 4 GB, three quarters free */
        xb_wr64(out, clusters);
        xb_wr64(out + 8, clusters / 4 * 3);
        xb_wr32(out + 16, spc);
        xb_wr32(out + 20, 512);
        return 24;
    case 5: { /* FileFsAttributeInformation: attributes, max name length, name (8-bit chars) */
        const char *fs = o && on_disc(o) ? "GDFX" : "FATX";
        if (len < 16) return 0;
        xb_wr32(out, 0);
        xb_wr32(out + 4, o && on_disc(o) ? 255 : 42);
        xb_wr32(out + 8, 4);
        memcpy(xb_mem + out + 12, fs, 4);
        return 16;
    }
    case 7: /* FileFsFullSizeInformation */
        xb_wr64(out, clusters);
        xb_wr64(out + 8, clusters / 4 * 3);
        xb_wr64(out + 16, clusters / 4 * 3);
        xb_wr32(out + 24, spc);
        xb_wr32(out + 28, 512);
        return 32;
    }
    rt_fatal(c, "volume information class %u not implemented", cls);
}

/* NtQueryVolumeInformationFile(FileHandle, IoStatusBlock*, FsInformation, Length, FsInformationClass) */
uint32_t k_file_NtQueryVolumeInformationFile(XbCtx *c) {
    uint32_t n = volume_info(c, rt_handle_get(ARG(0)), ARG(4), ARG(2), ARG(3));
    if (!n) return 0xC0000004u; /* STATUS_INFO_LENGTH_MISMATCH */
    io_status(ARG(1), STATUS_SUCCESS, n);
    return STATUS_SUCCESS;
}

/* IoQueryVolumeInformation(FileObject, FsInformationClass, Length, FsInformation, ReturnedLength*) */
uint32_t k_file_IoQueryVolumeInformation(XbCtx *c) {
    RtObject *o = rt_handle_get(rt_file_handle(ARG(0)));
    if (!o) return STATUS_INVALID_HANDLE;
    uint32_t n = volume_info(c, o, ARG(1), ARG(3), ARG(2));
    if (!n) return 0xC0000004u;
    if (ARG(4)) xb_wr32(ARG(4), n);
    return STATUS_SUCCESS;
}

/* ---- directory listings ---- */

typedef struct {
    DIR *d;
    char host[1200];
    char mask[256];
} Listing;

/* FATX and the disc match names case-insensitively; * and ? as in Win32. */
static int mask_match(const char *m, const char *s) {
    for (; *m; m++, s++) {
        if (*m == '*') {
            for (const char *t = s;; t++) {
                if (mask_match(m + 1, t)) return 1;
                if (!*t) return 0;
            }
        }
        if (!*s) return 0;
        if (*m != '?' && tolower((unsigned char)*m) != tolower((unsigned char)*s)) return 0;
    }
    return !*s;
}

void rt_listing_free(void *p) {
    Listing *l = p;
    if (!l) return;
    if (l->d) closedir(l->d);
    free(l);
}

/* NtQueryDirectoryFile(FileHandle, Event, ApcRoutine, ApcContext, IoStatusBlock*,
 *                      FileInformation, Length, FileInformationClass,
 *                      FileMask (OBJECT_STRING*), RestartScan)
 * One entry per call, as XAPI's FindFirstFile/FindNextFile use it. The
 * mask is taken on the first call or a restart. FileDirectoryInformation
 * (class 1): NextEntryOffset, FileIndex, four times, EndOfFile,
 * AllocationSize, FileAttributes, FileNameLength, then the name in 8-bit
 * characters, as on the Xbox. */
uint32_t k_file_NtQueryDirectoryFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_DIR) return STATUS_INVALID_HANDLE;
    uint32_t out = ARG(5), len = ARG(6), cls = ARG(7), mask = ARG(8), restart = ARG(9) & 0xFF;
    if (cls != 1) rt_fatal(c, "NtQueryDirectoryFile: class %u not implemented", cls);
    Listing *l = o->dir;
    int first = !l || restart;
    if (!l) {
        l = calloc(1, sizeof *l);
        o->dir = l;
        if (!host_path(o->path, l->host, sizeof l->host)) return STATUS_OBJECT_PATH_NOT_FOUND;
    }
    if (first) {
        if (l->d) closedir(l->d);
        l->d = opendir(l->host);
        if (mask && xb_rd16(mask)) snprintf(l->mask, sizeof l->mask, "%.*s", xb_rd16(mask), rt_str(xb_rd32(mask + 4)));
        else snprintf(l->mask, sizeof l->mask, "*");
    }
    struct dirent *e;
    while (l->d && (e = readdir(l->d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..") || !mask_match(l->mask, e->d_name)) continue;
        uint32_t n = (uint32_t)strlen(e->d_name);
        if (len < 64 + n) return 0x80000005u; /* STATUS_BUFFER_OVERFLOW */
        char full[1500];
        snprintf(full, sizeof full, "%s/%s", l->host, e->d_name);
        struct stat st = {0};
        stat(full, &st);
        memset(xb_mem + out, 0, 64);
        for (int i = 0; i < 4; i++) xb_wr64(out + 8 + 8 * i, 0x01C4F00000000000ull);
        xb_wr64(out + 40, (uint64_t)st.st_size);
        xb_wr64(out + 48, ((uint64_t)st.st_size + 0xFFF) & ~0xFFFull);
        xb_wr32(out + 56, S_ISDIR(st.st_mode) ? 0x10 : 0x80);
        xb_wr32(out + 60, n);
        memcpy(xb_mem + out + 64, e->d_name, n);
        io_status(ARG(4), STATUS_SUCCESS, 64 + n);
        rt_log("  listing %s: %s\n", o->path, e->d_name);
        return STATUS_SUCCESS;
    }
    uint32_t r = first ? 0xC000000Fu /* STATUS_NO_SUCH_FILE */ : STATUS_NO_MORE_FILES;
    io_status(ARG(4), r, 0);
    return r;
}

/* NtQueryFullAttributesFile(ObjectAttributes*, FILE_NETWORK_OPEN_INFORMATION*) */
uint32_t k_file_NtQueryFullAttributesFile(XbCtx *c) {
    char xbox[600], host[1200];
    rt_object_name(ARG(0), xbox, sizeof xbox);
    struct stat st;
    if (!host_path(xbox, host, sizeof host) || stat(host, &st) != 0) {
        rt_log("  attributes of %s: not found\n", xbox);
        return STATUS_OBJECT_NAME_NOT_FOUND;
    }
    write_times_and_sizes(ARG(1), (uint64_t)st.st_size, S_ISDIR(st.st_mode));
    return STATUS_SUCCESS;
}

/* NtOpenSymbolicLinkObject(LinkHandle*, ObjectAttributes*) */
uint32_t k_file_NtOpenSymbolicLinkObject(XbCtx *c) {
    char name[600];
    rt_object_name(ARG(1), name, sizeof name);
    for (int i = 0; i < nlinks; i++) {
        if (!strcasecmp(links[i].link, name)) {
            uint32_t h = rt_handle_new(OBJ_SYMLINK);
            rt_handle_get(h)->path = strdup(links[i].target);
            xb_wr32(ARG(0), h);
            return STATUS_SUCCESS;
        }
    }
    return STATUS_OBJECT_NAME_NOT_FOUND;
}

/* NtQuerySymbolicLinkObject(LinkHandle, LinkTarget STRING*, ReturnedLength*) */
uint32_t k_file_NtQuerySymbolicLinkObject(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_SYMLINK) return STATUS_INVALID_HANDLE;
    uint32_t s = ARG(1), n = (uint32_t)strlen(o->path);
    if (xb_rd16(s + 2) < n) return 0x80000005u; /* STATUS_BUFFER_OVERFLOW */
    memcpy(xb_mem + xb_rd32(s + 4), o->path, n);
    xb_wr16(s, n);
    if (ARG(2)) xb_wr32(ARG(2), n);
    return STATUS_SUCCESS;
}
