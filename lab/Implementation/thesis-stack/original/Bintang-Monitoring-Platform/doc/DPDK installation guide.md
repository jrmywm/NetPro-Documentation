# DPDK Installation
### **Reference**
- [DPDK installation guide](https://www.youtube.com/watch?v=0yDdMWQPCOI)

- [DPDK Download](http://core.dpdk.org/download/)

- [DPDK Quick Start Guide](http://core.dpdk.org/doc/quick-start/)

## **System Requirements**

### **Library**

1. C compiler
    
    ```bash
    apt install build-essential
    ```
    
2. Python 3.6 or later
    
    ```bash
    python3 --version
    //if python3 isn't installed use
    sudo apt install pyhton3
    ```
    
3. Meson (0.53.2+) and ninja
    
    ```bash
    sudo apt install meson
    sudo wget -qO /usr/local/bin/ninja.gz https://github.com/ninja-build/ninja/releases/latest/download/ninja-linux.zip
    sudo gunzip /usr/local/bin/ninja.gz
    sudo chmod a+x /usr/local/bin/ninja
    ninja --version
    ```
    
4. pyelftools (version 0.22+)
    
    ```bash
    apt install python3-pyelftools
    ```
    
5. Library for handling NUMA (Non Uniform Memory Access)
    
    ```bash
    sudo apt-get update -y
    sudo apt-get install -y libnuma-dev
    ```
    

### **System Software**

1. Kernel version >= 4.14
    
    ```bash
    uname -r
    ```
    
2. glibc >= 2.7 (for features related to cpuset)
    
    ```bash
    ldd --version
    ```

**Optional**

install pkgconf

```bash
sudo apt install pkgconf
```

## **Quick Start Guide**

### **Installing**

1. Extract sources
    
    ```bash
    wget http://fast.dpdk.org/rel/dpdk-22.11.2.tar.xz
    tar xf dpdk-22.11.2.tar.xz
    cd dpdk-stable-22.11.2/
    ```
    
2. Build libraries, drivers and test applications.
    
    ```bash
    meson build
    ninja -C build
    ```
    
3. add build to global directory
    
    ```bash
    cd build
    sudo ninja install
    sudo ldconfig
    ```
    
4. To include the examples as part of the build, replace the meson command with:
    
    ```bash
    cd build
    meson configure -Dexamples=all
    ```

## **Verifing Installation**

### **Verify Port**

1. check the port available
    
    ```bash
    sudo -i
    dpdk-devbind.py -s
    ```  

### **Bind Interface**

<aside>
⚠️ This project using Vmware as VM manager. The default ethernet driver is e1000. it isn’t support DPDK or multiqueue so it has to change to use vmxnet3 by
</aside>


1. find xxx.vmx file and open with text editor
2. change this line
    ```bash
    ethernet1.virtualDev = "e1000" -> ethernet1.virtualDev = "vmxnet3"
    ```
    
3. save it and verify
    
    ```bash
    cat /proc/interrupts  | grep ens160
    56:         29        139   PCI-MSI 1572864-edge      ens160-rxtx-0
    57:         14         13   PCI-MSI 1572865-edge      ens160-rxtx-1
    58:          0          0   PCI-MSI 1572866-edge      ens160-event-2
    ```
    
4. shutdown the desired interface
    
    ```bash
    ifconfig
    ```
    
    shutdown the host only port
    
    ```bash
    ifconfig ens192 down
    ```
    
5. update modprobe
    
    ```bash
    modprobe uio
    modprobe uio_pci_generic
    ```
    
6. bind the port
    
    ```bash
    dpdk-devbind.py -b uio_pci_generic 0b:00.0
    ```
    
5. Reserve huge pages memory.
    
    ```bash
    dpdk-hugepages.py -p 1G --setup 2G
    ```
    
6. Run poll-mode driver test (with a cable between ports).
    
    ```bash
    sudo build/app/dpdk-testpmd -l 0-3 -n 4 -- -i --portmask=0x1 --nb-cores=2
    testpmd> show port stats all
    ######################## NIC statistics for port 0  ########################
    RX-packets: 0          RX-errors: 0         RX-bytes: 0
    TX-packets: 0          TX-errors: 0         TX-bytes: 0
    ############################################################################
    ######################## NIC statistics for port 1  ########################
    RX-packets: 0          RX-errors: 0         RX-bytes: 0
    TX-packets: 0          TX-errors: 0         TX-bytes: 0
    ############################################################################
    testpmd> start tx_first
    testpmd> stop
    ---------------------- Forward statistics for port 0  ----------------------
    RX-packets: 2377688        RX-dropped: 0             RX-total: 2377688
    TX-packets: 2007009        TX-dropped: 0             TX-total: 2007009
    ----------------------------------------------------------------------------
    ---------------------- Forward statistics for port 1  ----------------------
    RX-packets: 2006977        RX-dropped: 0             RX-total: 2006977
    TX-packets: 2377720        TX-dropped: 0             TX-total: 2377720
    ----------------------------------------------------------------------------
    +++++++++++++++ Accumulated forward statistics for all ports+++++++++++++++
    RX-packets: 4384665        RX-dropped: 0             RX-total: 4384665
    TX-packets: 4384729        TX-dropped: 0             TX-total: 4384729
    ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    ```
    