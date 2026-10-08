// offset 断点持久化：JSON 文件 + 原子写（tmp+rename），Agent 重启后续传。
package main

import (
	"encoding/json"
	"log"
	"os"
	"strconv"
	"sync"
)

type fileState struct {
	Offset int64  `json:"offset"`
	Inode  string `json:"inode"`
}

type Registry struct {
	path  string
	mu    sync.Mutex
	Files map[string]fileState // key: sourceID + "|" + filePath
	dirty bool
}

func NewRegistry(path string) *Registry {
	r := &Registry{path: path, Files: map[string]fileState{}}
	if raw, err := os.ReadFile(path); err == nil {
		if err := json.Unmarshal(raw, &r.Files); err != nil {
			log.Printf("断点文件损坏，重新采集: %v", err)
			r.Files = map[string]fileState{}
		}
	}
	return r
}

func regKey(sourceID int, file string) string {
	return strconv.Itoa(sourceID) + "|" + file
}

// Get 返回文件断点；unknown 表示首次采集（从文件末尾开始，不补历史）。
func (r *Registry) Get(sourceID int, file string) (fileState, bool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	st, ok := r.Files[regKey(sourceID, file)]
	return st, ok
}

func (r *Registry) Set(sourceID int, file string, st fileState) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.Files[regKey(sourceID, file)] = st
	r.dirty = true
}

// Save 原子落盘（仅在脏时）。
func (r *Registry) Save() {
	r.mu.Lock()
	defer r.mu.Unlock()
	if !r.dirty {
		return
	}
	raw, err := json.MarshalIndent(r.Files, "", "  ")
	if err != nil {
		return
	}
	tmp := r.path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o644); err != nil {
		log.Printf("断点保存失败: %v", err)
		return
	}
	if err := os.Rename(tmp, r.path); err != nil {
		log.Printf("断点重命名失败: %v", err)
		return
	}
	r.dirty = false
}
