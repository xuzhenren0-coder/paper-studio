# 晨读邮件开发状态

当前是已可本地核验的邮件核心，不是已上线的08:00服务。v0.1.1收录本目录开发模块，应用中尚无订阅入口，也未发送真实邮件。

## 已实现

- 100—150词、近一年、精选来源、具体原文版本CC BY 4.0/CC0且明确核验的内容门槛，节选与原文逐字匹配；不合格内容不进入正式发送。
- 根据同意提供的兴趣关键词选文，按DOI排除已投递／可能已投递的文章；候选不足返回空，不凑数。
- 邮件HTML与纯文本正文，包含中英标题、出处、原文位置、节选、译文、3术语、思考题和退订链接；内容转义，无脚本和追踪图片。
- 阿里DirectMail经典RPC签名及单收件人发送适配器，AddressType=1，不将公共域代发擅自映射为0。默认禁止真实发送，日志不输出密钥、签名或完整请求。
- 08:00—10:00北京时间的补发窗口（08:00目标触发，10:00后不发送陈旧晨读）；唯一“邮箱＋日期”占用记录。发送后仅标已提交，超时记unknown且不自动重发。

## 仍需完成后才能上线

1. 自动选文／翻译准备任务与已核验的可分发论文池。模型生成译文不等于已完成专业核验；不能用这个演示材料当真实论文。
2. 公共HTTPS订阅确认、退订入口及真实有效退订测试。正式发送会拒绝示例退订地址。
3. 云端持久、原子共享存储与FC部署。store.py中的LocalStore仅用于本地验证；FC临时目录和进程变量不能承担多实例防重。
4. 发件地址、地域、专用最小权限服务凭据及模型凭据的安全配置；不能将密钥放入GitHub或Windows下载包。
5. 首封仅向用户指定的本人邮箱测试，经用户明确同意后才执行；随后验证QQ等实际收件箱结果，再邀请确认订阅的其他用户。
6. 按实际云账单核对首月50元目标，设置人数、调用及发送上限和告警。当前没有创建云函数、定时触发器或发送任务。

云函数准备任务目标07:30，发送目标08:00，均显式用Asia/Shanghai时区。定时触发只控制提交时刻，不能保证邮箱准时到达。FC事件可能重复执行；DirectMail没有客户端幂等参数，unknown记录必须先查询供应商日志，不能直接重发。

## 本地预览

在项目使用的Python环境中运行 `python tools/preview_morning_mail.py`，生成test-results/morning-preview/morning.html与纯文本。该内容是原创测试材料，明确标注，不是真实论文，也不会发到邮箱。

参考官方文档：
- https://help.aliyun.com/zh/direct-mail/api-dm-2015-11-23-singlesendmail
- https://help.aliyun.com/zh/direct-mail/signature
- https://help.aliyun.com/zh/direct-mail/sample-signature-request
- https://help.aliyun.com/zh/direct-mail/user-guide/setup-sender-addresses
- https://help.aliyun.com/zh/functioncompute/time-triggers
