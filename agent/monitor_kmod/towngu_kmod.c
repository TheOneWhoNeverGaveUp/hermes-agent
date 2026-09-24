#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/timekeeping.h>

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Towngu & Felix");
MODULE_DESCRIPTION("Deep system monitoring — CPU, thermal, battery, network");
MODULE_VERSION("0.3");

#define PROC_NAME "towngu_monitor"

static struct proc_dir_entry *proc_entry;

/* ── helpers ───────────────────────────────────────────────────────────── */

static int read_file_to_buf(const char *path, char *buf, int max_len)
{
    struct file *f;
    int ret;
    loff_t pos = 0;

    f = filp_open(path, O_RDONLY, 0);
    if (IS_ERR(f))
        return PTR_ERR(f);

    ret = kernel_read(f, buf, max_len - 1, &pos);
    filp_close(f, NULL);

    if (ret >= 0)
        buf[ret] = '\0';
    return ret;
}

static long read_file_long(const char *path)
{
    char buf[64];
    int ret;
    long val;

    ret = read_file_to_buf(path, buf, sizeof(buf));
    if (ret < 0)
        return ret;

    buf[strcspn(buf, "\n")] = '\0';
    if (kstrtol(buf, 10, &val) < 0)
        return -EINVAL;
    return val;
}

static int read_file_string(const char *path, char *buf, int max_len)
{
    int ret = read_file_to_buf(path, buf, max_len);
    if (ret >= 0)
        buf[strcspn(buf, "\n")] = '\0';
    return ret;
}

/* ── /proc/towngu_monitor ─────────────────────────────────────────────── */

static int towngu_show(struct seq_file *m, void *v)
{
    char buf[256];
    char path[256];
    int i, ret;
    long val;

    seq_puts(m, "=== Towngu Deep Monitor ===\n\n");

    /* ── CPU Info ─────────────────────────────────────────────────────── */
    seq_puts(m, "[CPU]\n");

    ret = read_file_string("/proc/cpuinfo", buf, sizeof(buf));
    if (ret >= 0) {
        char *line = buf;
        char *next;
        int cpus = 0;

        while (line && *line) {
            next = strchr(line, '\n');
            if (next)
                *next++ = '\0';

            if (strstr(line, "model name") || strstr(line, "cpu MHz") ||
                strstr(line, "cache size") || strstr(line, "bogomips") ||
                strstr(line, "processor")) {
                seq_printf(m, "  %s\n", line);
                if (strstr(line, "processor"))
                    cpus++;
            }
            line = next;
        }
        seq_printf(m, "  online: %d\n", num_online_cpus());
    }

    /* CPU load */
    ret = read_file_to_buf("/proc/loadavg", buf, sizeof(buf));
    if (ret >= 0) {
        buf[strcspn(buf, "\n")] = '\0';
        seq_printf(m, "  loadavg: %s\n", buf);
    }

    /* ── HWMON ────────────────────────────────────────────────────────── */
    seq_puts(m, "\n[HWMON]\n");

    for (i = 0; i < 32; i++) {
        char name[32];

        snprintf(path, sizeof(path), "/sys/class/hwmon/hwmon%d/name", i);
        ret = read_file_string(path, name, sizeof(name));
        if (ret < 0)
            continue;

        seq_printf(m, "  hwmon%d (%s):\n", i, name);

        for (int j = 0; j < 32; j++) {
            snprintf(path, sizeof(path),
                     "/sys/class/hwmon/hwmon%d/temp%d_input", i, j);
            val = read_file_long(path);
            if (val > 0)
                seq_printf(m, "    temp%d: %ld mC\n", j, val);
        }

        for (int j = 0; j < 32; j++) {
            snprintf(path, sizeof(path),
                     "/sys/class/hwmon/hwmon%d/in%d_input", i, j);
            val = read_file_long(path);
            if (val > 0)
                seq_printf(m, "    in%d: %ld mV\n", j, val);
        }

        for (int j = 0; j < 32; j++) {
            snprintf(path, sizeof(path),
                     "/sys/class/hwmon/hwmon%d/curr%d_input", i, j);
            val = read_file_long(path);
            if (val > 0)
                seq_printf(m, "    curr%d: %ld mA\n", j, val);
        }

        for (int j = 0; j < 32; j++) {
            snprintf(path, sizeof(path),
                     "/sys/class/hwmon/hwmon%d/fan%d_input", i, j);
            val = read_file_long(path);
            if (val > 0)
                seq_printf(m, "    fan%d: %ld RPM\n", j, val);
        }
    }

    /* ── THERMAL ──────────────────────────────────────────────────────── */
    seq_puts(m, "\n[THERMAL]\n");

    for (i = 0; i < 32; i++) {
        char type[64];

        snprintf(path, sizeof(path),
                 "/sys/class/thermal/thermal_zone%d/type", i);
        ret = read_file_string(path, type, sizeof(type));
        if (ret < 0)
            continue;

        snprintf(path, sizeof(path),
                 "/sys/class/thermal/thermal_zone%d/temp", i);
        val = read_file_long(path);
        if (val > 0)
            seq_printf(m, "  thermal_zone%d (%s): %ld mC (%ld C)\n",
                       i, type, val, val / 1000);
    }

    /* ── COOLING ──────────────────────────────────────────────────────── */
    seq_puts(m, "\n[COOLING]\n");

    for (i = 0; i < 32; i++) {
        char ctype[64];

        snprintf(path, sizeof(path),
                 "/sys/class/cooling_device%d/type", i);
        ret = read_file_string(path, ctype, sizeof(ctype));
        if (ret < 0)
            continue;

        snprintf(path, sizeof(path),
                 "/sys/class/cooling_device%d/cur_state", i);
        val = read_file_long(path);
        seq_printf(m, "  cooling_device%d (%s): state=%ld\n",
                    i, ctype, val);
    }

    /* ── BATTERY ──────────────────────────────────────────────────────── */
    seq_puts(m, "\n[POWER]\n");

    snprintf(path, sizeof(path),
             "/sys/class/power_supply/ACAD/online");
    val = read_file_long(path);
    seq_printf(m, "  ACAD: online=%ld\n", val);

    for (i = 0; i < 32; i++) {
        char status[32];
        char technology[64];

        snprintf(path, sizeof(path),
                 "/sys/class/power_supply/BAT%d/status", i);
        ret = read_file_string(path, status, sizeof(status));
        if (ret < 0)
            continue;

        seq_printf(m, "\n  BAT%d (%s):\n", i, status);

        snprintf(path, sizeof(path),
                 "/sys/class/power_supply/BAT%d/capacity", i);
        val = read_file_long(path);
        if (val >= 0)
            seq_printf(m, "    capacity: %ld%%\n", val);

        snprintf(path, sizeof(path),
                 "/sys/class/power_supply/BAT%d/voltage_now", i);
        val = read_file_long(path);
        if (val > 0)
            seq_printf(m, "    voltage: %ld uV\n", val);

        snprintf(path, sizeof(path),
                 "/sys/class/power_supply/BAT%d/current_now", i);
        val = read_file_long(path);
        if (val > 0)
            seq_printf(m, "    current: %ld uA\n", val);

        snprintf(path, sizeof(path),
                 "/sys/class/power_supply/BAT%d/temp", i);
        val = read_file_long(path);
        if (val > 0)
            seq_printf(m, "    temp: %ld mC\n", val);

        snprintf(path, sizeof(path),
                 "/sys/class/power_supply/BAT%d/technology", i);
        ret = read_file_string(path, technology, sizeof(technology));
        if (ret >= 0 && technology[0])
            seq_printf(m, "    technology: %s\n", technology);
    }

    /* ── MEMORY ───────────────────────────────────────────────────────── */
    seq_puts(m, "\n[MEMORY]\n");

    ret = read_file_to_buf("/proc/meminfo", buf, sizeof(buf));
    if (ret >= 0) {
        char *line = buf;
        char *next;

        while (line && *line) {
            next = strchr(line, '\n');
            if (next)
                *next++ = '\0';

            if (strstr(line, "MemTotal") || strstr(line, "MemFree") ||
                strstr(line, "MemAvailable") || strstr(line, "Buffers") ||
                strstr(line, "Cached") || strstr(line, "SwapTotal")) {
                seq_printf(m, "  %s\n", line);
            }
            line = next;
        }
    }

    /* ── NETWORK ──────────────────────────────────────────────────────── */
    seq_puts(m, "\n[NETWORK]\n");

    ret = read_file_to_buf("/proc/net/dev", buf, sizeof(buf));
    if (ret >= 0) {
        char *line = buf;
        char *next;

        /* Skip header lines */
        for (i = 0; i < 2 && line; i++) {
            next = strchr(line, '\n');
            if (next)
                line = next + 1;
        }

        while (line && *line) {
            next = strchr(line, '\n');
            if (next)
                *next++ = '\0';

            if (line[0] && line[strspn(line, ' ')])
                seq_printf(m, "  %s\n", line);
            line = next;
        }
    }

    /* ── Uptime ───────────────────────────────────────────────────────── */
    seq_puts(m, "\n[UPTIME]\n");

    {
        ktime_t uptime = ktime_get_boottime();
        long secs = ktime_to_ns(uptime) / NSEC_PER_SEC;

        seq_printf(m, "  uptime_seconds: %ld\n", secs);
        seq_printf(m, "  uptime_human: %ld days %02ld:%02ld:%02ld\n",
                   secs / 86400, (secs % 86400) / 3600,
                   (secs % 3600) / 60, secs % 60);
    }

    return 0;
}

static int towngu_open(struct inode *inode, struct file *file)
{
    return single_open(file, towngu_show, NULL);
}

static const struct proc_ops towngu_ops = {
    .proc_open = towngu_open,
    .proc_read = seq_read,
    .proc_lseek = seq_lseek,
    .proc_release = single_release,
};

/* ── Module init/exit ─────────────────────────────────────────────────── */

static int __init towngu_init(void)
{
    proc_entry = proc_create(PROC_NAME, 0444, NULL, &towngu_ops);
    if (!proc_entry) {
        pr_warn("towngu_monitor: failed to create /proc/%s\n", PROC_NAME);
        return -ENOMEM;
    }
    pr_info("towngu_monitor: /proc/%s created — monitoring active\n",
            PROC_NAME);
    return 0;
}

static void __exit towngu_exit(void)
{
    proc_remove(proc_entry);
    pr_info("towngu_monitor: removed\n");
}

module_init(towngu_init);
module_exit(towngu_exit);
