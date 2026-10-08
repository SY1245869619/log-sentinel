// GBK 解码（日志文件可能为 GBK 编码，统一转 UTF-8 上报）。
package main

import (
	"golang.org/x/text/encoding/simplifiedchinese"
	"golang.org/x/text/transform"
)

func decodeGBK(raw []byte) string {
	out, _, err := transform.Bytes(simplifiedchinese.GBK.NewDecoder(), raw)
	if err != nil {
		return string(raw) // 解码失败保底原文，避免丢数据
	}
	return string(out)
}
