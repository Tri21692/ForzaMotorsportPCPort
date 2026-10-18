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
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <unistd.h>

#include "rt.h"

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

/* Find a host path for a device-relative name, matching each component
 * case-insensitively. Missing trailing components are kept as written,
 * so creating a new file works. */
static int host_path(const char *xbox, char *out, size_t n) {
    char dev[600];
    resolve_links(xbox, dev, sizeof dev);
    const char *rest;
    char root[1100];
    if (!strncasecmp(dev, "\\Device\\CdRom0", 14)) {
        snprintf(root, sizeof root, "%s", disc_dir);
        rest = dev + 14;
    } else if (!strncasecmp(dev, "\\Device\\Harddisk0\\Partition", 27)) {
        int part = atoi(dev + 27);
        snprintf(root, sizeof root, "%s/Partition%d", hdd_dir, part);
        mkdir(hdd_dir, 0755);
        mkdir(root, 0755);
        rest = dev + 27;
        while (*rest >= '0' && *rest <= '9') rest++;
    } else {
        return 0;
    }
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
        const char *match = comp;
        struct dirent *e;
        while (d && (e = readdir(d))) {
            if (!strcasecmp(e->d_name, comp)) {
                match = e->d_name;
                break;
            }
        }
        size_t len = strlen(out);
        snprintf(out + len, n - len, "/%s", match);
        if (d) closedir(d);
    }
    return 1;
}

uint32_t rt_open(uint32_t *handle, uint32_t oa, uint32_t disposition, uint32_t options, uint32_t *info) {
    char xbox[600], host[1200];
    rt_object_name(oa, xbox, sizeof xbox);
    if (!host_path(xbox, host, sizeof host)) {
        rt_log("  open %s: no such device\n", xbox);
        return STATUS_OBJECT_PATH_NOT_FOUND;
    }
    struct stat st;
    int exists = stat(host, &st) == 0;
    int is_dir = exists && S_ISDIR(st.st_mode);
    if ((options & 0x40) && is_dir) return STATUS_ACCESS_DENIED; /* FILE_NON_DIRECTORY_FILE */
    int flags = O_RDWR;
    switch (disposition) {
    case 0: case 5: flags |= O_CREAT | O_TRUNC; break; /* SUPERSEDE, OVERWRITE_IF */
    case 1: if (!exists) goto missing; break;          /* OPEN */
    case 2: if (exists) return STATUS_OBJECT_NAME_COLLISION; flags |= O_CREAT; break;
    case 3: flags |= O_CREAT; break;                   /* OPEN_IF */
    case 4: if (!exists) goto missing; flags |= O_TRUNC; break;
    }
    uint32_t h;
    if (is_dir || ((options & 0x1) && !exists)) { /* FILE_DIRECTORY_FILE */
        if (!exists && mkdir(host, 0755) != 0) return STATUS_OBJECT_PATH_NOT_FOUND;
        h = rt_handle_new(OBJ_DIR);
    } else {
        int fd = open(host, flags, 0644);
        if (fd < 0 && (errno == EACCES || errno == EROFS)) fd = open(host, O_RDONLY); /* a read-only disc copy */
        if (fd < 0) goto missing;
        h = rt_handle_new(OBJ_FILE);
        rt_handle_get(h)->fd = fd;
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
    uint32_t r = rt_open(&h, ARG(2), ARG(7), ARG(8), &info);
    if (r == STATUS_SUCCESS) xb_wr32(ARG(0), h);
    io_status(ARG(3), r, info);
    return r;
}

/* NtOpenFile(FileHandle*, DesiredAccess, ObjectAttributes*, IoStatusBlock*, ShareAccess, OpenOptions) */
uint32_t k_file_NtOpenFile(XbCtx *c) {
    uint32_t h = 0, info = 0;
    uint32_t r = rt_open(&h, ARG(2), 1, ARG(5), &info);
    if (r == STATUS_SUCCESS) xb_wr32(ARG(0), h);
    io_status(ARG(3), r, info);
    return r;
}

/* NtReadFile(FileHandle, Event, ApcRoutine, ApcContext, IoStatusBlock*, Buffer, Length, ByteOffset*) */
uint32_t k_file_NtReadFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_FILE) return STATUS_INVALID_HANDLE;
    uint64_t pos = ARG(7) ? xb_rd64(ARG(7)) : o->pos;
    ssize_t n = pread(o->fd, xb_mem + ARG(5), ARG(6), (off_t)pos);
    if (n < 0) n = 0;
    o->pos = pos + (uint64_t)n;
    uint32_t r = n == 0 && ARG(6) ? STATUS_END_OF_FILE : STATUS_SUCCESS;
    io_status(ARG(4), r, (uint32_t)n);
    if (ARG(1)) {
        RtObject *e = rt_handle_get(ARG(1));
        if (e) e->signaled = 1;
        pthread_cond_broadcast(&rt_changed);
    }
    if (ARG(2)) rt_log("  NtReadFile: completion routine %08x not called yet\n", ARG(2));
    return r;
}

uint32_t k_file_NtWriteFile(XbCtx *c) {
    RtObject *o = rt_handle_get(ARG(0));
    if (!o || o->type != OBJ_FILE) return STATUS_INVALID_HANDLE;
    uint64_t pos = ARG(7) ? xb_rd64(ARG(7)) : o->pos;
    ssize_t n = pwrite(o->fd, xb_mem + ARG(5), ARG(6), (off_t)pos);
    if (n < 0) return STATUS_ACCESS_DENIED;
    o->pos = pos + (uint64_t)n;
    io_status(ARG(4), STATUS_SUCCESS, (uint32_t)n);
    if (ARG(1)) {
        RtObject *e = rt_handle_get(ARG(1));
        if (e) e->signaled = 1;
        pthread_cond_broadcast(&rt_changed);
    }
    return STATUS_SUCCESS;
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
    }
    rt_fatal(c, "NtSetInformationFile: class %u not implemented", cls);
}

/* NtQueryVolumeInformationFile(FileHandle, IoStatusBlock*, FsInformation, Length, FsInformationClass) */
uint32_t k_file_NtQueryVolumeInformationFile(XbCtx *c) {
    uint32_t out = ARG(2), cls = ARG(4);
    switch (cls) {
    case 3: /* FileFsSizeInformation: plenty of 16 KB clusters free */
        xb_wr64(out, 0x40000);
        xb_wr64(out + 8, 0x30000);
        xb_wr32(out + 16, 32);
        xb_wr32(out + 20, 512);
        io_status(ARG(1), 0, 24);
        return STATUS_SUCCESS;
    case 7: /* FileFsFullSizeInformation */
        xb_wr64(out, 0x40000);
        xb_wr64(out + 8, 0x30000);
        xb_wr64(out + 16, 0x30000);
        xb_wr32(out + 24, 32);
        xb_wr32(out + 28, 512);
        io_status(ARG(1), 0, 32);
        return STATUS_SUCCESS;
    }
    rt_fatal(c, "NtQueryVolumeInformationFile: class %u not implemented", cls);
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
