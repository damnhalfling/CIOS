#ifndef CIOS_LOG_H
#define CIOS_LOG_H

#include <stdio.h>
#include <time.h>

#define LOG_INFO(fmt, ...) \
    do { \
        time_t _t = time(NULL); \
        struct tm *_tm = localtime(&_t); \
        fprintf(stderr, "%02d:%02d:%02d [INFO] " fmt "\n", \
                _tm->tm_hour, _tm->tm_min, _tm->tm_sec, ##__VA_ARGS__); \
    } while (0)

#define LOG_WARN(fmt, ...) \
    do { \
        time_t _t = time(NULL); \
        struct tm *_tm = localtime(&_t); \
        fprintf(stderr, "%02d:%02d:%02d [WARN] " fmt "\n", \
                _tm->tm_hour, _tm->tm_min, _tm->tm_sec, ##__VA_ARGS__); \
    } while (0)

#define LOG_ERROR(fmt, ...) \
    do { \
        time_t _t = time(NULL); \
        struct tm *_tm = localtime(&_t); \
        fprintf(stderr, "%02d:%02d:%02d [ERROR] " fmt "\n", \
                _tm->tm_hour, _tm->tm_min, _tm->tm_sec, ##__VA_ARGS__); \
    } while (0)

#endif /* CIOS_LOG_H */
