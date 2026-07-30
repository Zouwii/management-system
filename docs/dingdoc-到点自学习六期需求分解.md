# **修订记录**

| 版本 | 作者 | 时间 | 说明 |
|------|------|------|------|
| V1.0 | @邹宏睿 | [2025-12-15] | 初版 |



# **项目概述**

## **项目背景**

<span style="color: rgba(0, 0, 0, 0.85);">针对自学习五期项目，及远舢、LG 现场叉车应用中自学习环节遇到的问题，我们开展第6期专项对到点自学习功能进行开发和优化。</span>

## **项目目标**
- 完成以下功能的开发和优化：
    1. 自学习和carly界面优化
        - 到点自学习界面，自学习开关增加提示帮助
        - 自学习数据分析界面，优化界面并增加提示
        - 自学习界面区分有码/无码补偿，并增加筛选框
        - 清空补偿数据按钮功能修改为补偿值置0
    2. 误差分析结论界面和后端开发
        - 控制误差、定位误差分析后端开发
    3. 自学习后端优化
        - 调度资源block修改，变成收敛后自动结束学习
        - 自学习过程异常数据阈值过滤
        - 自学习示教值发生变化，清空对应的补偿值和原始值
    4. 本体功能优化
        - 从3代机型参数中修改到点精度判断的阈值
        - 叉车库区补偿方案
- 以上所有功能合入到2603版本中。



# **需求清单**

## 自学习和carly界面优化

### **到点自学习界面，自学习开关增加提示帮助**

📋**需求描述**<li>目前自学习**计算开关/使用开关**没有解释说明，使用者可能不理解具体含义</li>
📌**任务清单**<li>☑ 前端界面增加两个开关说明@邹宏睿</li>

:::
方案：
1. <span style="color: rgb(56, 56, 56);">增加问号提示，鼠标靠近会弹出中文提示</span>

<span style="color: rgb(56, 56, 56);">“开启开关后，该车辆点位会进行补偿值计算”</span>

<span style="color: rgb(56, 56, 56);">“开启开关后，补偿值会通过一键下发发送到车上”</span>

![Gemini_Generated_Image_g6y3idg6y3idg6y3.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/f4b2bd5a-5760-45a9-a88d-758ed15ebd88.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=2yZ%2BhYxfavAHHl6hr%2BBzYPvrjwA%3D "")
:::

### 学习数据分析界面，优化界面并增加提示

📋**需求描述**<li>自学习分析界面，目前需要先点击分析，下次进入的时候才能点击查询，不方便使用。</li>
📌**任务清单**<li>☑ 自学习数据分析界面优化@邹宏睿</li><li>“分析”按钮改名为“更新”</li><li>在更新按钮旁边增加提示帮助，显示开关含义</li><li>点击查询后，若该地图未进行更新，则弹出提示“该地图数据未进行更新，需先点击更新按钮”。同时界面保留现状。</li>

:::
📈**示意图**

“更新并筛选出应用最新补偿值的数据”

![Gemini_Generated_Image_vx5snpvx5snpvx5s.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/b70b5eb7-1c80-4f8c-b792-c978f42e9aec.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=shWJoXWU8EvOSewGmMxp4C%2FHPW0%3D "")
:::

### <span style="color: rgb(56, 56, 56);">**自学习界面区分有码/无码补偿，并增加筛选框**</span>

📋**需求描述**<li>目前自学习界面无法区分有码/无码自学习，现场有筛选出无码点位然后手动修改补偿值的需求，故应该修改自学习界面显示。</li>
📌**任务清单**<li>☑ 增加筛选框选择有码/无码@邹宏睿</li>

📈**示意****图**![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/19b739ee-b873-4abb-87e9-099e77fb17aa.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=AyMO3mkOUgKq1nAl1d0XMs0Qb7o%3D "")注：需要确保全局开关只对查询出来的数据有效

### <span style="background-color: #FFFFFF;">清空补偿数据按钮功能修改为补偿值置0</span>

📋**需求描述**<li>无码自学习需要将补偿值置为0。原先的清除补偿值是将这一条点位信息直接清掉，没有置0的功能。</li><li>使用方法：置0之后，需要关闭计算开关，才能保证补偿值一直为0，否则一旦计算补偿值，就会变成非0。</li>
📌**任务清单**<li>☑ 对于单条数据的置0开发@邹宏睿</li><li>☑  对于所有点/异常点的置0开发@邹宏睿</li>

📈**示意****图**![unnamed2.jpeg](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/4cc52234-3392-4d4d-a390-756b2008b522.jpeg?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=jpqqQYdXfCCMZwfdwf0G4O%2FhPkY%3D "")![61a6aaa249bc2c3c13aef1e8a5935600.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/79ad05fa-ea7c-450d-9578-eafe2f0bd445.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=o0AoE0kgO1W86Ty0zMOi1FSIZPg%3D "")方案：【1】在全局计算开关、全局使用开关的右侧，有个全局置0开关。上面的开关都是自由开启关闭的。【2】下拉框里面取消“置0所有点补偿值”、“置0异常点补偿值”。【3】单条点位表格，在计算开关的左侧增加置0开关。其中，开启了置0开关就无法开启计算开关。【4】分栏里面维持清空数据、置0补偿数据按钮。

## **误差分析结论界面和后端开发**

### **控制误差、定位误差分析前、后端开发**

📋**需求描述**<li>自学习在部署阶段，需要进行控制误差、定位误差分析，用于提高现场实施效率。预期显示控制误差、定位误差、有码误差三个分栏，分栏内包含车辆健康度诊断和路径健康度诊断。</li>【采集的数据能不能说明车的问题】【验收标准待补充】
📌**任务清单**<li>☑ 精度分析前端界面开发@邹宏睿</li><li>☑ 精度分析后端开发@邹宏睿</li>

方案：<li>1. 计划增加一个精度分析界面，界面有闭环误差、控制误差、定位误差三个分栏。</li><li style="margin-left:1em">1. 闭环误差：（只限有码）指相机看到码的误差，代表最终的到点情况。</li><li style="margin-left:1em">2. 控制误差：（有码/无码）本体层面的控制误差，代表了车辆的到点能力。</li><li style="margin-left:1em">3. 定位误差：（只限有码）实际含义为闭环误差-控制误差，表示车辆在定位上的误差。</li><li>2. 对于每一类的误差情况界面，都包括车辆健康度诊断和路径健康度诊断。</li><li style="margin-left:1em">4. 车辆诊断包括表格和文字结论，表格可以根据精度、抖动、极值进行排序，危险、中等危险、健康的车辆分别显示为红色、黄色、绿色。</li><li style="margin-left:1em">5. 路径诊断包括前点-\>点位，以及均值、极值、标准差，危险、中等危险、健康的路径分别显示为红色、黄色、绿色。</li><li style="margin-left:1em">6. 界面右上角有设置按钮，里面储存着车辆不同判断标准阈值和路径不同健康判断标准阈值</li><li>3. 排序方法和阈值设置方法：</li><li style="margin-left:1em">7. 排序方法</li>
| <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**误差类型**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**排序指标 (Priority 1)**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**排序指标 (Priority 2)**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**业务逻辑解释**</span> |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| <span style="color: rgb(31, 31, 31);">**闭环误差**</span> | <span style="color: rgb(31, 31, 31);">**标准差 (Std Dev) 降序**</span> | <span style="color: rgb(31, 31, 31);">均值 (Mean) 降序</span> | <span style="color: rgb(31, 31, 31);">闭环误差主要看</span><span style="color: rgb(31, 31, 31);">**系统稳定性**</span><span style="color: rgb(31, 31, 31);">。如果标准差大，说明控制发飘、震荡，这是最危险的。其次才看均值（稳态误差）。</span> |
| <span style="color: rgb(31, 31, 31);">**控制误差**</span> | <span style="color: rgb(31, 31, 31);">**最大值 (Max) 降序**</span> | <span style="color: rgb(31, 31, 31);">均值 (Mean) 降序</span> | <span style="color: rgb(31, 31, 31);">走路径主要怕</span><span style="color: rgb(31, 31, 31);">**撞墙**</span><span style="color: rgb(31, 31, 31);">。只要有一次瞬间偏离过大（Max \> 阈值），就可能导致事故。因此极值风险排第一。</span> |
| <span style="color: rgb(31, 31, 31);">**定位误差**</span> | <span style="color: rgb(31, 31, 31);">**均值 (Mean) 降序**</span> | <span style="color: rgb(31, 31, 31);">3σ (99.7%分位) 降序</span> | <span style="color: rgb(31, 31, 31);">定位主要看</span><span style="color: rgb(31, 31, 31);">**准确度**</span><span style="color: rgb(31, 31, 31);">。如果均值偏大，说明有系统性偏差（标定问题）。其次看跳变（3σ）。</span> |
<li style="margin-left:1em">8. 阈值设置方法。目前设定的是</li>阈值设定遵循 **“定位精度 \> 控制精度”** 的工程原则，并采用红黄绿三级分级。<li>🟢 **正常 (Green)**：指标优异，无需关注。</li><li>🟡 **关注 (Yellow)**：指标轻微偏离，建议纳入周检计划。</li><li>🔴 **严重 (Red)**：指标严重超标，存在安全隐患或故障风险，需立即检查。</li>【是否正常】>    
| <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**误差类型**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**关注指标**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**🟢 正常阈值**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**🟡 关注阈值**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**🔴 严重阈值**</span> | <span style="color: rgb(31, 31, 31); background-color: rgb(239, 239, 239);">**调整理由**</span> |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| <span style="color: rgb(31, 31, 31);">**定位误差**</span><br><span style="color: rgb(31, 31, 31);">(感知层)</span> | <span style="color: rgb(31, 31, 31);">**均值 (Mean)**</span> | <span style="color: rgb(31, 31, 31);">**\< 1.5 cm**</span> | <span style="color: rgb(31, 31, 31);">**1.5 ~ 2.0 cm**</span> | <span style="color: rgb(31, 31, 31);">**≥ 2.0 cm**</span> | <span style="color: rgb(31, 31, 31);">现状大部分在 1.3cm 左右。放宽至 1.5cm 以容忍现状，但 Robot 6 (1.96cm) 仍需报黄。</span> |
|  | <span style="color: rgb(31, 31, 31);">**标准差 (Std)**</span> | <span style="color: rgb(31, 31, 31);">**\< 0.8 cm**</span> | <span style="color: rgb(31, 31, 31);">**0.8 ~ 1.2 cm**</span> | <span style="color: rgb(31, 31, 31);">**≥ 1.2 cm**</span> | <span style="color: rgb(31, 31, 31);">Robot 6 的 Std 达到了 1.1cm，这反映了定位的不稳定性，需报黄。</span> |
| <span style="color: rgb(31, 31, 31);">**控制误差**</span><br><span style="color: rgb(31, 31, 31);">(执行层)</span> | <span style="color: rgb(31, 31, 31);">**最大值 (Max)**</span> | <span style="color: rgb(31, 31, 31);">**\< 4.0 cm**</span> | <span style="color: rgb(31, 31, 31);">**4.0 ~ 6.0 cm**</span> | <span style="color: rgb(31, 31, 31);">**≥ 6.0 cm**</span> | <span style="color: rgb(31, 31, 31);">控制层Max现状均 \<3.8cm，设 4.0cm 为绿线比较合理。</span> |
|  | <span style="color: rgb(31, 31, 31);">**均值 (Mean)**</span> | <span style="color: rgb(31, 31, 31);">**\< 1.5 cm**</span> | <span style="color: rgb(31, 31, 31);">**1.5 ~ 2.5 cm**</span> | <span style="color: rgb(31, 31, 31);">**≥ 2.5 cm**</span> | <span style="color: rgb(31, 31, 31);">Robot 4 (1.57cm) 会报黄，其他车报绿，符合筛选“个别差车”的目的。</span> |
| <span style="color: rgb(31, 31, 31);">**闭环误差**</span><br><span style="color: rgb(31, 31, 31);">(业务层)</span> | <span style="color: rgb(31, 31, 31);">**均值 (Mean)**</span> | <span style="color: rgb(31, 31, 31);">**\< 1.0 cm**</span> | <span style="color: rgb(31, 31, 31);">**1.0 ~ 2.0 cm**</span> | <span style="color: rgb(31, 31, 31);">**≥ 2.0 cm**</span> | <span style="color: rgb(31, 31, 31);">这是最终停车精度。大部分车能做到 0.5cm，所以 1.0cm 要求不过分。Robot 5 (1.17cm) 报黄。</span> |
|  | <span style="color: rgb(31, 31, 31);">**标准差 (Std)**</span> | <span style="color: rgb(31, 31, 31);">**\< 0.5 cm**</span> | <span style="color: rgb(31, 31, 31);">**0.5 ~ 1.0 cm**</span> | <span style="color: rgb(31, 31, 31);">**≥ 1.0 cm**</span> | <span style="color: rgb(31, 31, 31);">Robot 5, 6 的 Std \> 1.0cm，说明停车时在晃，必须报红/黄。</span> |
<li>4. 部署使用方法：</li><li style="margin-left:1em">9. 先用单台车将所有线路跑一遍，然后查看定位误差分栏里面的路径健康度诊断。对定位差的路径使用反光板等方法增强定位能力。</li><li style="margin-left:1em">10. 所有车辆都沿着线路跑5圈，然后可以通过闭环误差显示实际的到点情况。对于到点差的车辆，继续通过控制误差、定位误差进行分析，寻找精度差的原因。</li><li style="margin-left:1em">11. 后续可以使用精度分析长期监控车辆状态，若某时刻车辆控制误差变差，则考虑进行维修保养之类的工作。</li><li>5. 右侧分析内容</li>
|  |  | 车号/路径 | 内容 | 排查/整改建议 |
|---|---|-------------|------|-------------------|
| 车辆 | 闭环误差 | robot9 | 闭环误差过大 | 查看控制误差是否过大，如过大可能要调控制参数 |
|  | 控制误差 | robot9 | 控制误差大 | 研发排查 |
|  | 定位误差 |  |  |  |
| 路径 | 闭环误差 |  |  |  |
|  | ~~控制误差~~ |  |  |  |
|  | 定位误差 |  |  |  |
📈**示意图**
---
1.5 指标存在联动性，目前寻找出来五种场景：**车辆健康度诊断：（更多关注车体本身因素）****闭环误差：**闭环差，控制差，定位差，联系研发排查控制和定位是否异常闭环差，控制差，定位好，联系研发排查控制是否异常闭环差，控制好，定位差，联系研发排查定位是否异常**控制误差：**联系研发排查控制是否异常**定位误差：**联系研发排查定位是否异常**路径健康度诊断：（更多关注环境因素）****闭环误差：**闭环差，控制差，定位差，优先检查地面是否打滑以及环境参照物是否变化或不明显闭环差，控制差，定位好，优先检查地面是否打滑闭环差，控制好，定位差，优先检查环境参照物是否变化或不明显**控制误差：**优先检查地面是否打滑**定位误差：**优先检查环境参照物是否变化或不明显<span style="background-color: #ED7D33;">后续考虑加入【深度分析功能】，结合历史所有运行数据进行综合分析。</span>【1】robot1（无码场景），控制误差差，联系研发调整PID控制参数【2】robot2（有码场景），闭环误差差，控制误差差，联系研发调整PID控制参数【3】robot3（有码场景），闭环误差差，控制误差正常，定位误差差，~~重新标定相机~~
---
路径健康度诊断：【4】123-\>456，闭环误差MAX大，检查地面是否打滑，或该处二维码是否破损/反光【5】234-\>567，定位误差MEAN\>阈值（黄色），多车在此路段出现偏差，建议增加反光板辅助定位。
---
方案2：直接去掉文本框，替换为红色的提示按钮。鼠标靠近按钮后弹出结论分析。![7331baa2f54701c9b34d3d4d1be89e2c.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/dcc1e5b9-90db-458d-984f-95e9b658b45a.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=911dM7yNp6hvFN1LTO3auwpHGcc%3D "")![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/121bac26-ac65-4101-aae2-67463e1face4.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=6GBbrxXNtzDYO6iHyAcb2uQkQmI%3D "")关注两点：（1）左侧的红色感叹号，靠近会提示什么问题。取消右侧的文本框。（2）精度最差排序、抖动最严重排序、极值风险排序，选择什么模式就会高亮当前列、其他列颜色变浅。同时按照当前列的阈值进行红色、黄色、绿色划分。

## **自学习后端优化**

### <span style="color: rgb(56, 56, 56);">~~**调度资源block修改，变成收敛后自动结束学习【导入到云端组件标准化专项】**~~</span>

📋**需求描述**调度资源block补充开发，自学习在同一点位中连续三次收敛后，即可结束学习![a270a575e3279b91349c01c0f89f3103.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/3BMqYybBeyVxvqwZ/img/d573a30c-6583-4e4d-b943-b1c8c91650f8.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=83%2BpoHTmfOivtvSVqFkRjMYabxY%3D "")
📌**任务清单**<li>☐ 自学习后端开发@邹宏睿</li><li style="margin-left:1em">1. 自学习算法优化，测试welford方案或者平均窗口方案的有效性，若有效则替换 </li><li style="margin-left:1em">2. 自学习后端，触发补偿值计算模块变更开发。在连续三次收敛之后，返回终止任务消息给调度资源。同时需要考虑正常计算的收</li><li>☐ carly3D 开发@曾宏清</li><li style="margin-left:1em">1. 需要提供退出循环的机制。在调度资源返回break的时候可以退出循环</li>

📈**方案**![5daefa43117bf05109b8e27c42260aa9.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/56e894fe-9918-4b54-bf42-d8fbd05fa524.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=CzoVGP3d3gPs4G6QfmdBV5dhnJc%3D "")![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952B5j04Mlap/img/93a8c779-be1f-4063-9ad0-2adc9d40a15e.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=kvCU532hGh02Qg%2FA1i%2BWTFwH5XY%3D "")**自学习算法变更**<li>1. 若实车验证自学习welford方案或者平均窗口方案有效，则替换为上述算法</li><li>2. 若实车验证算法无法显著提升部署效率，则将自学习算法由原来的（5\+5）模式变更为（1\+1\+1）模式，每次采集一条原始值后进行计算。block默认写死次数15，终止次数由到点自学习根据收敛情况判断，预期是连续三次收敛就停止。</li>**触发补偿值计算模块变更**<li>1. 触发补偿值计算若已经收敛，会跳出循环。</li><li>2. carly3D对应逻辑修改，对触发补偿值计算模块的res=2的情形做标志位，下次进入循环的时候break</li><li>3. 自学习后端，在连续三次收敛需要退出时，返回</li><pre><code>{<br>  "ok": false,<br>  "msg": "数据异常需要中断任务，等等可供debug的信息",<br>  "abort": true<br>}</code></pre>

### ~~**自学习过程中异常数据阈值过滤**~~<span style="color: rgb(56, 56, 56);">~~**【导入到云端组件标准化专项】**~~</span>

📋**需求描述**<li>自学习过程中，偶尔因为场地或者人为原因产生的异常数据，不应该纳入计算中，否者影响收敛速度。</li>
📌**任务清单**<li>☐ 进行自学习后端计算模块异常数据过滤功能开发@邹宏睿</li>

📈**方案**在自学习界面做如下设计：<li>1.  点击“手动计算”按钮的时候，某些点位的异常数据没有纳入计算，此时应该通知自学习前端。【缺点是使用者不一定会登录自学习界面】</li><li>2. 修改调度资源block——do\_automate\_action 的返回，直接跳过这一次的计算，等待下次计算。</li>![a270a575e3279b91349c01c0f89f3103.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/3BMqYybBeyVxvqwZ/img/d573a30c-6583-4e4d-b943-b1c8c91650f8.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=83%2BpoHTmfOivtvSVqFkRjMYabxY%3D "")<li>3. 考虑基于机器学习获得样本空间的范围，进行阈值设定并过滤。该阈值可以在自学习后端中写死，也可以考虑在自学习前端中进行设置。</li><li style="margin-left:1em">1. 采集的超限数据会存储到raw\_data数据表中，但是不会参与补偿值计算（通过判断是否在范围内加入到计算列表中）</li>[我的流程图]

### <span style="color: rgb(56, 56, 56);">**自学习示教值发生变化，清空对应的原始值和补偿值**</span>

📋**需求描述**<li>若前端示教值发生修改时，对应自学习后端的原始值和补偿值要清空。</li><li><span style="background-color: #FE0300;">Carly端打开/关闭自学习以及有码无码切换时，自学习界面同步删除对应补偿值数据。</span></li>
📌**任务清单**<li>☐  自学习后端对应开发@邹宏睿</li><li>☐ map-master和map-cloud对应开发@沈旭东</li>

📈**方案**<span style="color: rgb(56, 56, 56);">**自学习示教值发生变化，清空对应的原始值和补偿值**</span><span style="color: rgb(56, 56, 56);">**整体逻辑：示教值变化-\>uuid变化-\>map-master通知自学习后端**</span>（1）自学习后端uuid变化后，map-master会通知自学习插件点位信息发生变更。自学习插件向云端map-master查询最新的点位uuid，与自学习数据库中的uuid做比较，有以下几种情况：【增】x\_y\_theta\_N1  -\>   x\_y\_theta\_N1\_N2   更新所有层的uuid【减】x\_y\_theta\_N1\_N2  -\> x\_y\_theta\_N1  哪层变，清除该层补偿值，同时其它层的uuid也要更新【变】x\_y\_theta\_N1\_N2  -\> x\_y\_theta\_N11\_N2  哪层变，清除该层补偿值，同时其它层的uuid也要更新
---
自学习后端严格数据库逻辑：【增】对raw\_data,该点位所有uuid更新。对learning\_result，该点位所有uuid更新。【减】x\_y\_theta\_N1\_N2  -\> x\_y\_theta\_N1 。对raw\_data，所有N2数据删掉，该点位其他uuid更新。对learning\_result，该点位楼层补偿值置0，uuid更新；该点位其他楼层uuid更新。【变】x\_y\_theta\_N1\_N2  -\> x\_y\_theta\_N11\_N2 。对raw\_data，所有N1数据删掉，该点位其他uuid更新。对learning\_result，，该点位楼层补偿值置0，uuid更新；该点位其他楼层uuid更新（2）map-master类似自学习插件的逻辑，需要清理本地map-master数据库和云端map-master数据库
---
**Carly端打开/关闭自学习以及有码无码切换时，自学习界面同步删除对应补偿值数据**<span style="color: rgb(56, 56, 56);">**整体逻辑：开关自学习/有码无码切换-\>compensation\_type变化-\>map-master通知自学习后端**</span>（1）自学习后端compensation\_type变化后，map-master会通知自学习插件点位信息发生变更。自学习插件向云端map-master查询最新的点位compensation\_type，与自学习数据库中的compensation\_type做比较，只要有变化，就删除该点位数据所有的原始数据和补偿数据。（2）map-master类似自学习插件的逻辑，需要清理本地map-master数据库和云端map-master数据库

## **本体功能优化**

### **从3代机型参数中修改到点精度判断的阈值**

📋**需求描述**<li>到点精度判断阈值，支持从3代机型参数中配置</li>
📌**任务清单**<li>☑ nav-manager做对应开发@邹宏睿</li>

:::
方案：
1. jcar3-params增加到点精度阈值

名称：navigation/control/reach\_tolerance
2. nav-manager中增加对该阈值的使用
:::

### **叉车轨迹整体补偿**

📋**需求描述**<li><span style="color: rgb(38, 38, 38);">叉车进库位轨迹，如果只补偿终点，会导致AGV进入库位车身歪的问题</span>，<span style="color: rgb(38, 38, 38);">需要对路径上前置点位也进行部分补偿，使得入库时车身不歪。</span></li><li><span style="color: rgb(38, 38, 38);">不支持非库区</span></li>
📌**任务清单**<li>☐ nav-manager开发@邹宏睿</li><li>1. 地图热更新读取库区内容</li><li>2. 搜路层库区重合路径查找匹配</li><li>3. 对重合路径应用自学习 </li><li>☐ 功能联调@邹宏睿</li><li>☐ 到点自学习属性作为库区非共享参数@王鸿博</li>![image.png](https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/mxPOG5z6ZzK9bnKa/img/df5edee3-ac13-4813-87f3-6800d1812a39.png?Expires=1785406292&OSSAccessKeyId=LTAI5tKTjg4Kq1HCdBJ8qpSp&Signature=TNZaocRgyhR%2BPgcvpgFNdjSvh38%3D "")**风险点：**目前库区点位属性是在库区模板中编辑，如果库区模板实例化后自学习示教值不一样，无需创建不同库区模板（到点自学习开关是点位属性）。本期按免示教方式处理（认为不同点位自学习示教值一致）。结论：<li>1. 进入库区导航拿到最终的终点才能进行补偿，使用终点补偿值进行补偿。</li><li>2. 等待carly3D 高位货架专项合入2512，即可实现自学习和库区的解耦。</li>

:::
方案：
- 终点补偿对前置点影响有多少，需要进行关联，比如终点补偿了(x, y, yaw)。前面几个点会受到影响，需要进行标记和关联。这样处理的话工作量就会特别大。
- 如果将该功能和库区模板关联起来，就可以将信息进行复用。若需要实现局部拓扑网补偿偏移，只对库区里面的拓扑路径生效，只要有一个点位有补偿值，那么库区中的所有拓扑点位都会进行补偿和偏移。
- 库区的特性：
    - 单库位
    - 只有一个终点可以补偿，~~且~~~~目标点为朝向和线路是平行或者垂直关系~~
        - 一个库区里面如果有多个点打开补偿值时需报错
        - 比如一个模板里面有两个点位A,B存在补偿值，一开始到A按A补偿值生效，再从A到点B，按B补偿生效，这个时候小车就不一定在A上面了，可能会触发上道。
    - 起点是从主干道连过来的
    - 拓扑是横平竖直的关系

---

细化问题：

1、库区补偿点进出都需要补偿；

2、识别补偿点属于库区点位，库区所有点位都需要进行同样的偏移；

3、库区和外面的连接点会出现不平滑现象，存在风险点。
:::

📈**示意****图**[我的流程图][我的流程图]nav-manager方案细化：（1）在地图热更新的时候，用结构体储存库区数组。例如【3,4,5】、【6,7】【8,9】 <pre><code>&#91;{<br>  "storage&#95;area&#95;data": "",<br>  "storage&#95;area&#95;id": 130,<br>  "storage&#95;area&#95;name": "1",<br>  "storage&#95;area&#95;nodes": &#91;<br>    3,<br>    4,<br>    5<br>  ],<br>  "temp&#95;field": ""<br>}]</code></pre>（2）判断终点开启补偿/起点开启补偿（3）判断终点在库区/起点在库区，找到库区的数组。例如【3,4,5】（4）导航下发路径中，如果有和库区数组匹配上的途经点，就都使用补偿值。例如【3,4】

### **非共享参数协议变更**

:::
4.24 **库区非共享参数列表设计和协议（增补协议）**

**背景描述：**

目前库区的非共享参数只包含库区公共属性，不包含点位、线路属性。原有方案设计将自学习补偿值作为库区非共享参数，会造成地图数据库校验失败报错。

**解决方案：**

新增非共享参数列表字段（non\_shared\_parameter\_list），储存点位、线路的非共享参数。

前端目前采用覆盖设计。状态时序如下：
1. 检查库区变更，将库区内容定制覆盖到点位。
2. 如果点位中含有“点位非共享参数”，前端库区变更不覆盖点位的数值。例如：前端检查到non\_shared\_parameter\_list中，runlearning为1，则选择不将库区该内容覆盖到点位上。
3. 前端将聚合数据设置到地图端。

地图端处理如下：

（1）地图端只检查“库区共享参数”，不检查“点位共享参数”。

**协议：**

```cpp
{
    "non_shared_parameter_list": {   //新增：非共享参数列表
        "point_params": {
            "runLearing": 1,        // 0 表示没有改动过，和模板一致，策略为受模板影响。1表示改动过，和模板不一致，策略为不受模板影响。
        },
        "line_params": {}
    },
    "lc_exception_params": {}    //库区非共享参数列表
}
```

**前端对应应该保留原点位内容：**@王鸿博@沈旭东

```c++
{
  "run_learning_pose":[{"index":1,"theta":0,"x":0,"y":0}],   //示教值
  "compensation_type": 1, //自学习补偿开关
}
```
:::









# **软件版本**
- 基于新carly 2512
- 合入3.2603



# **项目计划**
- 需求分解：[2025-12-17]
- 测试用例评审：[2025-08-08]
- 软件功能交付：[2026-02-07]
- 测试完成时间：[2025-09-18]
- 验收时间：[2026-03-20]

@张艺曦调整时间

# **相关人员**
- 项目经理：@张艺曦
- 产品经理：@裘鹏程
- 软件技术经理：@伍浩贤
- 研发工程师：@邹宏睿@刘闯@沈旭东@曾宏清
- 测试：

# **合入版本**
- 新carly 2603
