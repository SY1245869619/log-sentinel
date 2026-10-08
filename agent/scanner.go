// 目录扫描：管理端"一键扫描"时列出目录下的日志文件。
package main

import (
	"os"
	"path/filepath"
	"strings"
)

const (
	scanMaxFiles = 2000
	scanMaxDepth = 6
)

// ScanDir 递归列出目录下的文件（限深限数，只返回常规文件）。
func ScanDir(root string) []string {
	var out []string
	root = filepath.Clean(root)
	baseDepth := len(strings.Split(root, string(filepath.Separator)))
	_ = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		depth := len(strings.Split(path, string(filepath.Separator))) - baseDepth
		if d.IsDir() {
			if depth > scanMaxDepth {
				return filepath.SkipDir
			}
			return nil
		}
		if !d.Type().IsRegular() {
			return nil
		}
		if len(out) < scanMaxFiles {
			out = append(out, path)
		}
		return nil
	})
	return out
}
