/* Networking: XNet and Winsock, replaced (HLE).
 *
 * Xbox Live is gone and system link is not supported, so the runtime
 * presents a console with no network cable. XNet's own startup is not
 * run (its code is not all discovered, and it would program the network
 * hardware). Startup calls succeed, the link reports down, which is what
 * games check before they use the network, and sockets cannot be made.
 *
 * Each replacement is a stdcall function: it reads its arguments from the
 * guest stack and pops them, as the code it replaces would.
 */
#include <string.h>

#include "names.h"
#include "rt.h"

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))

static void ret(XbCtx *c, uint32_t eax, uint32_t argbytes) {
    c->eax = eax;
    c->esp += 4 + argbytes;
}

#ifdef XB_FN_XNetStartup
/* INT XNetStartup(const XNetStartupParams *) */
void XB_FN_XNetStartup(XbCtx *c) {
    rt_log("XNetStartup (HLE): no network\n");
    ret(c, 0, 4);
}
#endif

#ifdef XB_FN_WSAStartup
/* int WSAStartup(WORD wVersionRequested, LPWSADATA): fill in version 2.2. */
void XB_FN_WSAStartup(XbCtx *c) {
    uint32_t d = ARG(1);
    if (d) {
        memset(xb_mem + d, 0, 2 + 2 + 257 + 129 + 2 + 2 + 4);
        xb_wr16(d, 0x0202);
        xb_wr16(d + 2, 0x0202);
    }
    ret(c, 0, 8);
}
#endif

#ifdef XB_FN_XNetGetEthernetLinkStatus
/* DWORD XNetGetEthernetLinkStatus(void): 0, no cable. */
void XB_FN_XNetGetEthernetLinkStatus(XbCtx *c) { ret(c, 0, 0); }
#endif

#ifdef XB_FN_socket
/* SOCKET socket(int af, int type, int protocol): INVALID_SOCKET. */
void XB_FN_socket(XbCtx *c) {
    rt_log("socket (HLE): no network\n");
    ret(c, 0xFFFFFFFFu, 12);
}
#endif
