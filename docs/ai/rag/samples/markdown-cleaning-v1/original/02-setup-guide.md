文档校验：詹剑波 @ 20240913

# **前言**

本文档用以说明EMMA本体软件的部署过程。主要概述为以下步骤：
    - 硬件准备
    - 软件系统准备
    - 迦智自研软件安装
    - 机型配置
    - 场景配置
    - 测试和应用

# **Setup步骤**

## **2.1 硬件准备**

硬件准备包括如下内容：
    - 整车零部件、传感器、核心控制器等硬件设备准备
    - 电气系统准备
    - 组装准备

原生的硬件准备，即按照设计图纸组装出完整的机器人。在硬件准备阶段，需要同时进行硬件的初始准备工作，主要是指特定的零部件和设备需要并行进行准备工作，主要包括：

| 编号 | 设备 | 准备工作 |
|------|------|------------|
| 1 | 工控机 | 硬盘/EMMC预装软件系统<br>参考：<br><ul><li>X86工控机：[再生龙操作系统备份还原方法](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=3QD5Ea7xAo4VEjrYwdv9JG1YBwgnNKb0&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc) 或 硬盘对拷方法</li><br><li>KM车板子：[3399+A311D备份还原烧写-机器人系统现场维护指南（KM车）](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=mdvQnONayjBJKea5Z5rLWPY2MeXzp5o0&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)</li><br><li>KM2代板子： [3588系统备份还原烧写-机器人系统现场维护指南（KM2代）](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=QOG9lyrgJP3grzaPiGYoQ20LVzN67Mw4&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)</li></ul> |
| 2 | 激光雷达 | 预设基础的配置，比如IP（需遵循IP要求规范，参考对应标准文件） |
| 3 | 相机 | 部分相机需要预先标定内参，参考对应标准文件和方法 |
|  |  |  |

## **2.2 软件系统准备**

在2.1步骤中一般通过镜像的方式，完成工控机的准备工作。对于镜像系统的选择，<span style="color: #FE0300;"><u>**截止到20251213**</u></span>，有如下选项（后续按需更新，资源获取联系管理员）

| 系统架构代号 | 镜像选择 |  | 主控说明 |
|------------------|------------|---|------------|
| classic/master | ubuntu16041-jz-emma-2-9.1.img.gz |  | 经典款工控机，CE主控，X86系统，ubuntu1604，VCU100，VCU200，VCU310 |
| ~~km/master~~<br>~~km/slaver1~~ | ~~ubuntu1604-jz-km-3399-1-9.20230414.img~~<br>~~ubuntu1604-jz-km-a311d-1-9.20230414.img~~ |  | ~~KM一代双板主控，3399\+A311d，arm64系统，ubuntu1604，VCU400~~ |
| km2/master | ubuntu1604-jz-hc-3588-1-10.20250617.img |  | VCU520，3588，arm64系统，K系列，ubuntu1604 |
| km2/master | ubuntu1604-jz-hc-2-3588-1-10.20250617.img |  | VCU500，3588，arm64系统，<br>下一代标车，下一代叉车，ubuntu1604 |
| km2/master | ubuntu1604-jz-hc-3-3588-1-10.20251202.img |  | VCU560，3588，arm64系统，狗系统专用，ubuntu1604 |
| km3/master | ubuntu2404-jz-hc-3588-1-11.20251027.img |  | VCU520，3588，arm64系统，K系列，ubuntu2404，ros2 |

一般在预先准备的软件系统中，已完成以下基础内容项：
    - 操作系统安装、迦智特有化定制（比如桌面，远程机制，基础系统管理）
    - 迦智特有的软件运行环境的预备安装（包括ROS环境、程序运行管理环境、依赖包环境）
    - 迦智自研软件系统jz-total的某一个稳定版

即，系统已经完成目标软件的90%左右内容，后续因为定制/升级等需求再更新软件，一般就是基于jz-total软件包进行一次小升级即可。

## **2.3 迦智自研软件安装和配置**

此部分的目标是完成单车软件构建。包括两部分内容，即嵌入式软件和固件更新，以及本体软件更新。

<u>***远期发展/标准品批量化，将考虑2.3.1和2.3.2全自动化（即用alice工具处理），目前暂时参考如下分步方法。***</u>

### **2.3.1 嵌入式软件/固件更新**

目前更新有两种方法，任选其一即可。

| 方法 | 方法介绍 |  |
|------|------------|---|
| 方法一 | 使用嵌入式提供的各项工具软件直接更新，参考对应标准文件和方法 |  |
| 方法二 | 使用alice工具直接进行更新，会自动完成特定机型全部的嵌入式软件和固件更新，参考对应标准文件和方法<br><u>*注意：只有标准车才支持alice工具更新。*</u> |  |

### **2.3.2 本体软件更新**

目前更新仅支持手动更新，暂不支持alice更新。步骤如下：
    1. SSH远程登录小车（或者串口终端登录小车）
    2. 检查架构名（一般系统预设过不需更改）
```shell
jz_total_distributed display

# x86显示 classic/master
# km1代显示 km/master
# km2代显示 km2/master
```
    3. 安装新软件
        1. 依据产品/项目需求，得到jz-total标准版本号
            1. 参考jz-total版本全列表：[jz-total release full log](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=jkB7yl4ZK3vV6olMB2gmJPMX2O6oxqw0&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)

            2. 参考jz-total版本全发布变更：[jz-total changelog](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=qnYMoO1rWxD4ja5rFZdYN6o0W47Z3je9&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)

            3. <u>**一般总是使用，已经发布的最新的LTS版本**</u>
        2. 安装jz-total
        3. 按需更新若干定制子包
```shell
# 对于x86车、km2代车，执行安装jz-total：
jz_total_deploy 版本号
jz_total_env_install

# 对于km1代车，执行安装jz-total
jz_total_km_deploy 版本号
jz_total_km_env_install

# 按需更新子包
jz_install 子包名 子包版本
jz_runtime_env_install 子包名
```
    4. 重启系统

## **2.4 机型配置**

此部分的目标是完成单车数据构建。包含三部分内容，即确定机型、配置机型、机型调参。

### **2.4.1 确定机型**

机型数据用于管理单车的所有配置项。机型按照不同类型有不同的确定方式：
- 标准车
    - 依据下单通知确定产品机型料号
    - 依据料号从 [机型release full log](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=Gl6Pm2Db8D37R49Mi6obKNKbJxLq0Ee4&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)
的"AMR产品软件机型管理"或"FOLA产品软件机型管理"页找到对应料号的软件机型即可
    - 若没有找到或信息为空，则联系研发添加（数据建设初期覆盖度低，一定阶段后会实现批量覆盖）
- 项目车（定制车）
    - 项目定制车总是基于某一个标准产品改造的，故可参考上文标准车方法找到其标准车原型的机型
    - 基于得到的标准车机型，按照下文2.4.2的方法直接进行定制化配置

### **2.4.2 配置机型**

确定机型名字后，即可按照下述方法机型配置：
- 标准车
    - 直接指令一键配置即可
```shell
emma_configure 机型名字
emma_restart
```
- 项目车（定制车）
    - 基于得到的标准车机型，创造一个新的定制车型，然后改造/配置的其他配置细节
    - 新机型名字命令规则参考：[机型setup指南](https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8azLmGpZC5Y6YwZ1WgN7R35y?utm_scene=team_space&iframeQuery=anchorId%3Duu_lysj99yzxoavgzgq14f)

        - 机型主名字：使用标准名字中的某一个，不可新造
        - 机型子名字：编号使用1000以上的范围
        - 机型子名字：特证名可自定义，推荐用项目简写，英文大写
        - 机型名字确定后，在 [机型release full log](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=Gl6Pm2Db8D37R49Mi6obKNKbJxLq0Ee4&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)
的"项目定制车软件机型管理"页添加以备忘
```shell
emma_create derive 标准机型名 新机型名字
emma_configure 新机型名字
emma_restart
```

### **2.4.3 机型调参**

需要进一步调配单车参数，以满足单车最终运行所需。调配方法有以下汇总：

| 编号 | 调配参数系统 | 调配参数内容 |
|------|------------------|------------------|
| 1 | adele系统 | <ul><li>jz-total\<=2.2308</li><br><li style="margin-left:1em">使用 adele1 系统进行调配</li><br><li style="margin-left:1em">可配置：</li><br><li style="margin-left:2em">90%左右的硬件参数</li><br><li style="margin-left:2em">标定调配需使用终端工具</li><br><li style="margin-left:2em">其他无法调配的参数使用终端工具</li><br><li>jz-total\>=2.2309</li><br><li style="margin-left:1em">使用 adele3 系统进行调配</li><br><li style="margin-left:1em">可配置：</li><br><li style="margin-left:2em">99%的硬件参数、软件参数</li><br><li style="margin-left:2em">其他无法调配的参数使用终端工具</li><br><li style="margin-left:1em">使用方法文档：[机型setup指南](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=EpGBa2Lm8azLmGpZC5Y6YwZ1WgN7R35y&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)</li></ul> |
| 2 | 终端工具 | <ul><li>jz-total\>=2.107</li><br><li style="margin-left:1em">标定终端工具可处理99%的标定 [标定测试文档 108版本](https://alidocs.dingtalk.com/api/doc/transit?dentryUuid=kDnRL6jAJM3vwG2LiNBr6meLWyMoPYe1&queryString=utm_medium%3Ddingdoc_doc_plugin_card%26utm_source%3Ddingdoc_doc)</li></ul> |
| 3 | 其他 | 其他未尽部分咨询研发 |

## **2.5 场景配置**

此部分的目标是完成场景数据构建。

核心内容为：<u>新建地图、编辑地图、简单跑图</u>，全部通过工具 Carly 系统交互式完成。
    - 新建地图
        - 新建地图完成，可验证EMMA核心功能（即感知相关）全量通过。
    - 编辑地图
        - 简单点位编辑完成，可验证EMMA基础工具相关通过。
    - 简单跑图
        - 简单跑图完成，可验证EMMA核心功能（即运动相关）全量通过。

可直接参考对应标准文档和方法。

## **2.6 测试和应用**

此部分的目标是完成复杂场景/项目场景的应用和测试。

核心内容为：业务编辑、调度任务、老化测试，通过 Carly 以及 Cloudia 系统交互式完成。
    - 业务编辑
        - 参考项目实际场景、任务，在生产和测试阶段进行真实模拟的业务设计，创造复杂的点位动作
    - 调度任务
        - 基于业务场景地图，多车接入调度，验证多车系统的业务成立
    - 老化测试
        - 基于业务和调度，进行老化任务测试，通过即最终大成。

可直接参考对应标准文档和方法。

# **Q&A**

 TODO











[]该文档24年末维护期间暂不更新（保持原样），以当前更新时间为准。
