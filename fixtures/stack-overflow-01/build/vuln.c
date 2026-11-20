/*
 * Reference C shape of the fixture. It is not the canonical builder: the
 * committed vuln.elf is produced by build_elf.py, because this host has no
 * i386 cross-compiler. The C source documents the intended observable behavior:
 *
 *   - buf is 32 bytes;
 *   - read() accepts 64 bytes into it (the defect);
 *   - a valid input of 0..32 bytes returns normally;
 *   - a 64-byte PoC overwrites the saved return address.
 *
 * Build on a Linux guest with:
 *   gcc -m32 -nostdlib -static -fno-pie -no-pie -fno-stack-protector \
 *       -O0 -o /tmp/vuln-c vuln.c
 * The exact bytes are NOT expected to match vuln.elf; use build_elf.py for the
 * pinned artifact.
 */

typedef unsigned int u32;

static int sys_read(int fd, void *buf, u32 count) {
    int ret;
    __asm__ volatile (
        "int $0x80"
        : "=a"(ret)
        : "a"(3), "b"(fd), "c"(buf), "d"(count)
        : "memory"
    );
    return ret;
}

static void sys_exit(int code) {
    __asm__ volatile (
        "int $0x80"
        :
        : "a"(1), "b"(code)
        : "memory"
    );
    __builtin_unreachable();
}

void vuln(void) {
    char buf[32];
    /* The defect: 64 bytes are allowed into a 32-byte stack buffer. */
    sys_read(0, buf, 64);
}

void _start(void) {
    vuln();
    sys_exit(0);
}
