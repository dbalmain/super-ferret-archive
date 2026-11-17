/* Fork after exec so Python's inherited high-water RSS cannot set the floor. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static double milliseconds(struct timespec t) {
    return (double)t.tv_sec * 1000.0 + (double)t.tv_nsec / 1000000.0;
}

int main(int argc, char **argv) {
    if (argc < 3) return 2;
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);
    pid_t child = fork();
    if (child == 0) {
        execvp(argv[2], argv + 2);
        perror("execvp");
        _exit(127);
    }
    if (child < 0) return 2;
    int status;
    struct rusage usage;
    while (wait4(child, &status, 0, &usage) < 0) {
        if (errno != EINTR) return 2;
    }
    clock_gettime(CLOCK_MONOTONIC, &end);
    FILE *out = fopen(argv[1], "w");
    if (!out) return 2;
    fprintf(out, "{\"wall_ms\": %.6f, \"peak_kib\": %ld}\n",
            milliseconds(end) - milliseconds(start), usage.ru_maxrss);
    fclose(out);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
