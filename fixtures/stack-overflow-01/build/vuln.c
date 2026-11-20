/* BUILD-ONLY. Never read by analysis, AI or the auditor. */
#include <stdio.h>
#include <string.h>

__attribute__((noinline))
static void handle(char *input)
{
    char buf[32];
    strcpy(buf, input);   /* CWE-121: unbounded copy into a 32-byte stack buffer */
    puts(buf);
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s <input>\n", argv[0]);
        return 2;
    }
    handle(argv[1]);
    return 0;
}
