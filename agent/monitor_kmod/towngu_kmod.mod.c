#include <linux/module.h>
#include <linux/export-internal.h>
#include <linux/compiler.h>

MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(".gnu.linkonce.this_module") = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};



static const struct modversion_info ____versions[]
__used __section("__versions") = {
	{ 0xbd03ed67, "__ref_stack_chk_guard" },
	{ 0x1cae9a42, "filp_open" },
	{ 0x4b5cc7c5, "kernel_read" },
	{ 0x9d52f437, "filp_close" },
	{ 0xd272d446, "__stack_chk_fail" },
	{ 0x6514c3b7, "strcspn" },
	{ 0x1f55c5b2, "kstrtoll" },
	{ 0x90a48d82, "__ubsan_handle_out_of_bounds" },
	{ 0x102ef4a9, "proc_remove" },
	{ 0x73d975eb, "seq_write" },
	{ 0xb61837ba, "seq_printf" },
	{ 0x296b9459, "strchr" },
	{ 0x17545440, "strstr" },
	{ 0x2182515b, "__num_online_cpus" },
	{ 0x40a621c5, "snprintf" },
	{ 0x12ca6142, "ktime_get_with_offset" },
	{ 0x9fdb9308, "strspn" },
	{ 0xaa9a3b35, "seq_read" },
	{ 0x253f0c1d, "seq_lseek" },
	{ 0x34d5450c, "single_release" },
	{ 0xd272d446, "__fentry__" },
	{ 0x80222ceb, "proc_create" },
	{ 0xe8213e80, "_printk" },
	{ 0xd272d446, "__x86_return_thunk" },
	{ 0xe931a49e, "single_open" },
	{ 0xbebe66ff, "module_layout" },
};

static const u32 ____version_ext_crcs[]
__used __section("__version_ext_crcs") = {
	0xbd03ed67,
	0x1cae9a42,
	0x4b5cc7c5,
	0x9d52f437,
	0xd272d446,
	0x6514c3b7,
	0x1f55c5b2,
	0x90a48d82,
	0x102ef4a9,
	0x73d975eb,
	0xb61837ba,
	0x296b9459,
	0x17545440,
	0x2182515b,
	0x40a621c5,
	0x12ca6142,
	0x9fdb9308,
	0xaa9a3b35,
	0x253f0c1d,
	0x34d5450c,
	0xd272d446,
	0x80222ceb,
	0xe8213e80,
	0xd272d446,
	0xe931a49e,
	0xbebe66ff,
};
static const char ____version_ext_names[]
__used __section("__version_ext_names") =
	"__ref_stack_chk_guard\0"
	"filp_open\0"
	"kernel_read\0"
	"filp_close\0"
	"__stack_chk_fail\0"
	"strcspn\0"
	"kstrtoll\0"
	"__ubsan_handle_out_of_bounds\0"
	"proc_remove\0"
	"seq_write\0"
	"seq_printf\0"
	"strchr\0"
	"strstr\0"
	"__num_online_cpus\0"
	"snprintf\0"
	"ktime_get_with_offset\0"
	"strspn\0"
	"seq_read\0"
	"seq_lseek\0"
	"single_release\0"
	"__fentry__\0"
	"proc_create\0"
	"_printk\0"
	"__x86_return_thunk\0"
	"single_open\0"
	"module_layout\0"
;

MODULE_INFO(depends, "");


MODULE_INFO(srcversion, "30727FE6035B990C0AF88F2");
