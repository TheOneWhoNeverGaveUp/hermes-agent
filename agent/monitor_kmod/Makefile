obj-m += towngu_kmod.o

KDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

load:
	sudo insmod towngu_kmod.ko
	cat /proc/towngu_monitor

unload:
	sudo rmmod towngu_kmod
