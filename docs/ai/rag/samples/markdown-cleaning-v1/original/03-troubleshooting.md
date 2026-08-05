## **任务流程图**

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/2M9qP5jow6da3O01/img/ffbe80c6-ae7c-4745-a476-b151b97364b8.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=lWrSlpLPMNqkx1IHE8swQv0bANQ%3D "")

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8K4nyRXA38zYqLbj/img/b9a2a34f-d703-4e88-b5e4-69dfe45a0b4a.png "")

图一 Web-Service框架图 

上图展示了Web-Service主要的框架：
1. WS主要通过TaskService、TaskNaviService、TaskActionService三个服务类
2. 三个服务分别通过“/webService/robotTask”，“/task/navi”，“/task/action” ROS服务向外提供了导航、动作、停止、状态等接口
3. 其中TaskService基于“/webService/robotTask”接口，属于老接口，目前主要由Carly以及三方开放接口模块调用
4. TaskNaviService、TaskActionService基于“/task/navi”，“/task/action” ，属于新接口，目前主要由调度系统使用
5. WS的具体任务处理通过Action类和PythonEngine完成，其中Action类根据导航类型分为导航、盲走、伺服三种不同的类型。
6. 机器人行为动作则通过PythonEngine调用Python脚本完成，脚本依赖的接口则通过wservice\_python\_module封装的接口实现。
7. 导航和动作的状态则通过Global类来实现，对外部的状态也通过该类获得。
8. NaviClient分装了导航相关的接口，包括发送导航目标，取消导航等。
9. WS通过封装嵌入提供的的接口来实现具体的行为控制和状态汇总。
10. 低代码则通过ROS:Param以及行为树TOPIC来实现控制
11. Carly和Agent状态信息也通过ROS服务实现交互
12. 所有上述过程均基于ROS服务实现

上述仅仅是一个概要的过程，实际交互逻辑会复杂的多，后续章节会详细介绍，总体来说，目前Web-Service作为本体的一个任务接收和处理的逻辑，起到逻辑中间件的作用，是嵌入式以及导航相应接口的桥梁，因此其存在依赖众多，逻辑复杂的情况；由于历史积累的原因，目前Web-Service依赖了100多个ROS接口或者变量，大部分依赖接口的文档缺失，有部分冗余无效的逻辑，需要考虑对其进行梳理和整理的需要。

## **任务处理**

### **导航与动作任务下发**

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8K4nyRXA38zYqLbj/img/61a8b8b1-953b-4e73-9dac-6756b269102e.png "")

图二 导航与动作任务下发

上图是WS开放的导航与动作任务的接收和处理过程，WS 提供三个不同的服务接口，分别是"/WebService/robotTask"、"/task/navi"、"/task/action"，其中第一个是老接口，主要由Carly、三方开放接口模块调用，后面两个是新接口，主要由调度系统调用：
1. 老接口流程：
    - "/WebService/robotTask" 可以处理导航和动作的启动、停止、状态等任务。
    - 收到指令后，通过判断请求结构体中的cmd字段判断是启动还是停止等任务类型，并通过poseId判断是否进行导航控制，如果进行导航控制创建一个MoveAction，并调用NaviClient的sendGoal方法，通过调用导航接口进行导航指令执行
    - 如果是停止任务，则直接调用NaviClient的cancelGoal函数停止导航，同时通过设置Global中的状态为Canceling来通知python脚本停止运行，也就是控制动作的取消。
    - 如果是获得状态，则通过调用Global的toJson方法转换为json字符串，这样通过pulish发布给其他模块
    - 对于动作指令，则是通过使用PythonEngine动态执行python脚本来实现。而python脚本依赖的底层嵌入式和从导航的调用则是通过上一节介绍的wservice\_python\_module封装的接口来实现。
2. 新接口流程：
    - 新接口直接将动作和导航分离，分别通过两个不同的接口进行调用，其指令的解析则在基类task\_base\_service中进行，同样通过cmd字段来判断针对导航或者动作的启动，停止还是状态获取。
    - 对于导航，则通过子类task\_navi\_service来处理，底层也是和老接口一样，通过MoveAction和NaviClient来实现，其状态则存储在TaskNaviGoal中
    - 对于动作，则通过子类task\_action\_service来处理，底层也和老接口一样依赖PythonEngine实现动作的解析和运行；运行状态存储在TaskActionGoal中。

#### **接口设计**

接口名称：/WebService/robotTask，/task/navi，/task/action

输入参数：

| 参数名称 | 参数类型 | 参数说明 |
|------------|------------|------------|
| cmd | string | 任务类型：start、stop、status、pause、history（Global中存储的历史状态）、delayStop（延时停止某个任务）、result（获得某个任务的状态） |
| task\_request | string | JSON格式数据，用于存放任务的详细信息，配置和其他相关属性 |



输出参数：jzws\_srvs::RobotTask::Response 任务执行结果，另外详细的执行状态通过cmd=status获得

#### **task\_request 参数**

接口名称：/WebService/robotTask

| 参数名 | 参数类型 | 参数说明 |
|---------|------------|------------|
| id | int | reuqestId -- 请求ID，单次请求唯一 |
| timeout | int | 任务执行超时时间， 如果设置则会等待任务完成后才返回，且如果超时，根据不同的策略选择忽略，报错或者重试 |
| from | string | 任务发起端名称：如 carly，yiwu 等 |
| prepare | int | 任务启动，等待毫秒数 |
| work\_map | string | 地图名称 |
| task\_list | json | 任务列表，内含参数 |
| cancels | json | 执行取消任务，看代码应该类似于回滚动作 |

task\_list 参数结构：

| 参数名称 | 参数类型 | 参数说明 |
|------------|------------|------------|
| action\_id | string | 动作/任务ID |
| poseId | int | 目标位置ID |
| action | string | 脚本名称 |
| use\_yaw | int | <span style="color: #C10002;">是否使用角度？</span> |
| \_id\_list | array | 路径点位列表 |

#### **时序图**

##### **导航时序**

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8K4nyRXA38zYqLbj/img/8ff9747c-cf67-41a7-8142-a5319127d3e5.png "")

图三 老接口导航时序图
1. carly发送导航指令给Webservice
2. ws 解析cmd决定使用什么指令完成任务
3. 如果收到的是开始指令，那么ws开始解析传入的task\_request参数，并解析为json对象
4. ws启动线程，并且此时直接返回任务接收成功给carly，carly开始使用cmd=status获得任务执行状态
5. ws线程继续执行导航逻辑，通过prepare参数决定等待时间
6. 等待结束，ws 遍历json中的task\_list开始执行单个任务
7. 如果task\_list中poseID不为空，则调用move2PoseId方法进行导航控制
8. ws 合成目标信息后，通过sendGoal方法发送给导航模块
9. 导航模块异步返回active事件，表示已经接收到指令
10. 导航模块在导航过程中，返回feedback事件，通知当前导航的动作步骤
11. ws 循环等待导航结束
12. 导航结束后，返回done事件给ws，ws结束等待
13. 在这个过程中carly通过status指令获得任务进展情况
14. 当整个任务执行完毕，carly会得到idle状态

##### **动作时序**

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8K4nyRXA38zYqLbj/img/f0bc6595-d6fe-403d-ab5d-a8ecfa5fd778.png "")

图四 老接口动作执行

动作接口实际上是上面启动接口的一个分支，主要是webservice判断action字段是否为空来决定是否执行动作
1. carly 发送任务给ws启动指令
2. ws 解析任务后通过map和action组装动作脚本路径并读取脚本内容
3. ws 执行脚本，脚本调用ws接口，间接调用嵌入式或者导航模块的ROS接口，ws接口会兼容不同的接口版本，抽象后对脚本开放
4. ws 封装的函数中会对Global的状态进行判断，并处理Canceling等状态，决定是否中断动作执行
5. Carly通过status获得任务执行的状态，并获得异常信息

##### **抢占时序**

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8K4nyRXA38zYqLbj/img/b449b683-6825-4f83-a938-c5ceff88c057.png "")

图五 抢占时序

新的导航接口和老接口有个本质的区别是，新接口支持抢占模式。
1. 新接口收到导航指令后，会检查缓存中是不是有正在执行的导航任务，如果存在，则将Global.preempt置为true
2. 正在执行的导航任务，如果发现该信号量为true，则终止等待，直接结束线程
3. 新的导航任务抢占成功，开始正常发送导航指令给导航模块

# **日志排查**

## **普通任务排查**

### **本机下发任务**

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/01135a95-5197-46c2-adf1-6cbe36212899.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=tpB0vTbYtQ5rin10tWoPtBgOYdQ%3D "")

上图展示了本机下发的任务，其中关键字为task request。from:carly 表示任务来源为carly

### **执行脚本**

### ![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/2fc18049-ab7a-47f7-b3b7-d3abec977058.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=i6YvuM1uh3rSXj4suCkjKqkSI3w%3D "")

上图展示了如何查看carly具体执行的脚本，可以通过脚本分析具体运行的block以及调用的函数

### **导航指令**

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/ec9b22f1-37d5-412e-ba3f-638c7e75e697.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=N3IqLwUZtDufSYdGQlqP0xppOoc%3D "")

上图展示了脚本中导航任务的下发，当看到navi client sending goal msg to action server说明任务已经下发导航，此时还要看后面日志中是否有navi action activate如果有，说明导航已经接受指令。

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/62583a44-87dc-4443-a986-0f082e2bb291.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=o84XLzaTRnBeSyfR90DnqEujLFM%3D "")

上图中导航收到了导航指令，并给出了回执。但是后面的日志显示任务被取消，原因是行为树报错。

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/26d419a4-4d04-4b8c-83ae-3b3c014a718c.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=OL0YF21EWZQ4d9YgEtywOeH2zqQ%3D "")

上面图中是导航正常结束的形式，可以看到action done succed关键字，如果整个任务执行完毕，则会显示task\_list execute successfully关键字

## **调度任务排查**

### **调度导航任务**

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/6725e84a-0d6e-4771-9e0b-3ca0ec5c59d0.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=s2dL7zHkva20%2Blh7V2KCTXlcNQ8%3D "")

上图展示了调度任务的指令关键词req.task\_request以及(start) navi，其中(start) navi表示是一个导航任务，如果是动作任务则为(start) action

导航任务后续的日志和上面本地的导航任务一致。

### **调度动作任务**

![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/eYVOLw3Y4z0Aqpz2/img/17293b24-de91-4dd3-86bb-70d5eb9bdb04.png?Expires=1785411489&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=rdxVqYSPv9%2FU1sxc7aguxkoU8nE%3D "")

上图是调度动作任务关键字，其后续日志参考本地的动作任务执行日志说明









[]该文档24年末维护期间暂不更新（保持原样），以当前更新时间为准。




