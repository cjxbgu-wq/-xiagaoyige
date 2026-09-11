//
//  ObfStr.h - 自动生成(gen_obf_src.py), 勿手改
//  全量字符串混淆运行时层: obfN(NSString)/obfC(C串)/obfCF(CFString)/obfSEL(SEL)
//  length 前缀解密(无 NUL 依赖), obfN per-id 缓存(热路径零分配)
//
#ifndef OBF_STR_H
#define OBF_STR_H

#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/runtime.h>

NSString *obfN(unsigned i);
const char *obfC(unsigned i, char *buf, unsigned bufSize);
CFStringRef obfCF(unsigned i);
SEL obfSEL(unsigned i);

// C 字符串字面量替换宏(块作用域复合字面量, 禁止用于静态初始化/长期存储)
#define OBCS(id) obfC((id), (char[256]){0}, 256)

#endif // OBF_STR_H
