//
//  VCamNotify.h
//  VCamPlus
//
//  通知管理（对标 vcameracrack.dylib 的 VCamNotify 类）
//
//  逆向特征：
//    - dispatch_queue: com.vcam.notify
//    - Darwin 通知名: com.vcam.ios.media.reload / com.vcam.ios.live.changed
//    - "Registered VCamNotify listener for reload-media"
//    - "State polling timer started" —— plist 轮询
//    - 状态备份路径: /var/mobile/vc.plist
//
//  注意（记忆约束）：
//    - mediaserverd 中 Darwin 通知可能触发崩溃，所以 mediaserverd 主要用 plist 轮询
//    - SpringBoard 中可以用 Darwin 通知
//

#import <Foundation/Foundation.h>

// Darwin 通知名（与原版保持一致）
extern NSString *const VCamNotifyReloadMedia;   // com.vcam.ios.media.reload
extern NSString *const VCamNotifyLiveChanged;   // com.vcam.ios.live.changed

// plist 路径（逆向确认）
extern NSString *const VCamPlistPath;            // /var/mobile/Media/DCIM/vc.plist
extern NSString *const VCamStateBackupPath;      // /var/mobile/vc.plist

typedef void(^VCamNotifyCallback)(NSString *name);

@interface VCamNotify : NSObject

+ (instancetype)sharedInstance;

#pragma mark - Darwin 通知
- (void)postNotification:(NSString *)name;
- (NSInteger)registerForNotification:(NSString *)name callback:(VCamNotifyCallback)callback;
- (void)unregisterNotification:(NSString *)name token:(NSInteger)token;

#pragma mark - plist 轮询（mediaserverd 安全通道）
// 逆向特征: "State polling timer started" —— 每秒检查 vc.plist 的 enabled 字段
- (void)startPollingWithInterval:(NSTimeInterval)interval
                        callback:(void(^)(BOOL enabled))callback;
- (void)stopPolling;

// 打光专用快速轮询(1.3.45): lightColor 跟随屏幕闪烁 0.1s 级变化, 主轮询
// 0.15s 节拍跟不上 → 独立 timer 高频(0.04s)只同步打光 7 键。
// 挂与主轮询同一串行队列: 两个 timer handler 天然互斥, 无并发问题
- (void)startLightPollingWithInterval:(NSTimeInterval)interval
                             callback:(void(^)(NSDictionary *plist))callback;
- (void)stopLightPolling;

#pragma mark - plist 读写
+ (BOOL)isPlistEnabled;
+ (void)setPlistEnabled:(BOOL)enabled;
+ (NSString *)activePlaybackPath;
+ (void)setActivePlaybackPath:(NSString *)path;
// 旋转/镜像状态（跨进程同步: 悬浮球在 SpringBoard 写, mediaserverd 轮询读;
// 字段名对齐千面逆向 vc.plist 的 manualRotation）
+ (NSInteger)plistRotation;
+ (void)setPlistRotation:(NSInteger)degrees;
+ (BOOL)plistMirrored;
+ (void)setPlistMirrored:(BOOL)mirrored;

// 用户画面变换(悬浮球 箭头/＋/−/复): pan 归一化 -1..1(自由平移),
// zoom 0.5..4.0(1=原始); mediaserverd 轮询读 → 黑底画布合成
+ (double)plistPanX;
+ (void)setPlistPanX:(double)panX;
+ (double)plistPanY;
+ (void)setPlistPanY:(double)panY;
+ (double)plistZoom;
+ (void)setPlistZoom:(double)zoom;
+ (void)resetPlistTransform;
// 前置方向修正(2026-08-23): 前置摄像头流的显示旋转与后置差 180°(实测 pan 双反),
// mediaserverd 无法自动判别前后置 —— 悬浮窗长按箭头切换(1.3.53), 开启时 pan 应用时 X/Y 同时取反
+ (BOOL)plistFrontPanFix;
+ (void)setPlistFrontPanFix:(BOOL)fix;

// 播放控制（跨进程: 悬浮球写, mediaserverd 轮询应用）
// paused: 暂停/继续视频解码(暂停时预渲染冻结在最后一帧)
+ (BOOL)plistPaused;
+ (void)setPlistPaused:(BOOL)paused;
// restartToken: 自增令牌, mediaserverd 检测到变化后从头重播当前视频
+ (NSInteger)plistRestartToken;
+ (void)bumpRestartToken;

// 三色打光(1.3.37, 跨进程: 悬浮球屏幕取色检测写, mediaserverd 轮询应用):
// lightEnabled=取色总开关; lightColor=0x00RRGGBB(0=熄灭, 颜色跟随屏幕闪烁);
// lightX/lightY=光斑中心 %(默认 50/50); lightIntensity 强度%(默认 30);
// lightDiameter 直径%(默认 48); lightFeather 羽化%(默认 100)
+ (BOOL)plistLightEnabled;
+ (void)setPlistLightEnabled:(BOOL)enabled;
+ (uint32_t)plistLightColor;
+ (void)setPlistLightColor:(uint32_t)color;
+ (int)plistLightX;
+ (void)setPlistLightX:(int)x;
+ (int)plistLightY;
+ (void)setPlistLightY:(int)y;
+ (int)plistLightIntensity;
+ (void)setPlistLightIntensity:(int)v;
+ (int)plistLightDiameter;
+ (void)setPlistLightDiameter:(int)v;
+ (int)plistLightFeather;
+ (void)setPlistLightFeather:(int)v;

#pragma mark - 密钥验证(HMAC-SHA256 / 离线验签 / 短卡密)
// 体系(核心加固):
//   卡密 = 16位十六进制 (XXXX-XXXX-XXXX-XXXX)，内含 HMAC-SHA256 签名
//   byte0 = 计划类型(0时/1天/2月/3永久), byte1-2 = 随机数, byte3-7 = HMAC签名
//   SECRET = 32字节固定密钥，与 PC端生成器、CardKeyGuard.xm 完全一致
//   无需公钥、无需设备码绑定、无需 T_enc、无需 ECDSA
//   激活后按计划类型计时；换卡重新激活
+ (NSString *)vcamDeviceCode;                     // 16 hex 大写(设备码 raw，兼容保留)
+ (BOOL)vcamLicenseValid;                         // 已激活(每次重验签+过期检查, 0.5s 节流)
+ (BOOL)vcamActivateLicense:(NSString *)input;    // 激活(验签通过写 licBlob/activated_at/plan)
+ (void)vcamPublishDeviceCode;                    // SB 侧发布 dcPub(md 互证用)
+ (BOOL)vcamCrossDeviceCodeOK;                    // md 侧: dcPub 与本机一致
// 1.3.78 新增: 月卡过期支持
+ (NSString *)vcamLicensePlanFromBlob:(NSString *)blob;  // 解析 blob 中的计划类型
+ (NSDictionary *)vcamLicenseExpiryInfoFromBlob:(NSString *)blob; // 兼容旧版，返回 nil
+ (BOOL)vcamLicenseCheckExpiry:(NSString *)blob;                 // 检查许可证是否过期

// 1.3.63 方案A(密钥参与功能解密): blob v2 = 签名 + T_enc 参数密文,
// 验签通过才能解密出功能真值 —— 跳过验证 = 参数全垃圾(画面数学错误)。
// 布局(gen_license.py T_TRUE): idx1-6 打光色/ idx7 HSV 门限/ idx8 计票
// 阈值/ idx9-11 zoom ×100/ idx12 pan ×100/ idx13 旋转步进/ idx14-15 羽化
// 分子分母。Double 版本 = u32/100(定点); Int 版本 = u32 原值(颜色/门限)
+ (double)vcamLicenseTableDouble:(NSUInteger)idx; // ×100 定点参数取值
+ (uint32_t)vcamLicenseTableInt:(NSUInteger)idx;  // 整数参数取值(颜色/门限)
// 1.3.78 栈式解码(明文不驻留内存): 解码直写调用方 uint32_t[18] 缓冲,
// 调用方读值后须自行 memset 擦除; 失败时函数内部已擦
+ (BOOL)vcamLicenseDecodeT:(uint32_t *)outT;

#pragma mark - 1.3.65 前台 App 进程取色采样器 + mmap 颜色总线
// 根因(1.3.64 设备日志实锤): UICSI 在 SB 进程只截 SB 自己的图层 ——
// App 前台时采样区全黑(color=0x000000 cnt=0), 颜色永远到不了视频。
// 1.3.44 时期的 441/441 "成功"是桌面层颜色的假阳性。
// 方案: 检测搬到前台 App 进程内(进程内 UICSI 截的是本 App 画面 = 屏幕
// 实际内容), 结果写 mmap 共享页(零磁盘写, 25Hz 无 disk writes 限额风险),
// mediaserverd 0.02s 光轮询读总线打光。SB 检测同时双写总线(桌面模式)。
+ (void)vcamStartAppSampler;                     // App 进程采样器(Tweak.m 调)
+ (int)vcamAppSampleSlotAtX:(double)px               // 采样一拍(进程内 UICSI, 返色档)
                          Y:(double)py;
+ (void)vcamNotifyPickSlot:(int)slot;            // Darwin 通知色档上行(沙盒保底)
+ (void)vcamStartPickRelay;                      // SB 端中继(7 slot→总线)
+ (void)vcamPublishPickCfg:(BOOL)on              // SB→App 配置下行(Darwin+state
                       X:(double)px                  // 沙盒安全; 坐标随 state 传递)
                       Y:(double)py;
+ (void)vcamPickPublishSlot:(int)slot            // 写端: 采样器/SB/relay 双写
                      color:(uint32_t)color          // (color=标准纯色, 原版逻辑)
                      count:(int)cnt
                         avg:(uint32_t)avg;
+ (BOOL)vcamPickSharedColor:(uint32_t *)outColor // 读端: md 光轮询(≤1s 新鲜,
                      count:(int *)outCount;         // outColor 直接可打光)
+ (uint32_t)vcamMatchKnownLightShared:(const uint8_t *)rgba  // 共享颜色匹配
                                    n:(int)n
                            outBestIdx:(int *)outBestIdx
                               outCount:(int *)outCount
                                  outAvg:(uint32_t *)outAvg;

@end
