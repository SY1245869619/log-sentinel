// 日志 tail 采集：glob 匹配、多行堆栈合并、轮转检测、断点续传。
package main

import (
	"bufio"
	"io"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

const (
	maxMultilineLines = 200    // 单条目最多合并行数
	entryFlushQuiet   = time.Second
	saveStateEvery    = 5 * time.Second
)

// ---------------- 管理器 ----------------

type TailerManager struct {
	sender   *Sender
	registry *Registry
	mu       sync.Mutex
	workers  map[int]*tailWorker // key: sourceID
}

func NewTailerManager(sender *Sender, registry *Registry) *TailerManager {
	return &TailerManager{sender: sender, registry: registry, workers: map[int]*tailWorker{}}
}

// Sync 与最新配置对齐：新增的启动、移除的停止、变化的重启。
func (m *TailerManager) Sync(sources []SourceConfig) {
	m.mu.Lock()
	defer m.mu.Unlock()
	want := map[int]SourceConfig{}
	for _, s := range sources {
		want[s.SourceID] = s
	}
	for id, w := range m.workers {
		if _, ok := want[id]; !ok {
			w.stop()
			delete(m.workers, id)
			log.Printf("日志源 %d 已移除，停止采集", id)
		}
	}
	for id, s := range want {
		if w, ok := m.workers[id]; ok && w.sameConfig(s) {
			continue
		}
		if w, ok := m.workers[id]; ok {
			w.stop()
		}
		tw := newTailWorker(s, m.sender, m.registry)
		m.workers[id] = tw
		go tw.run()
		log.Printf("日志源 %d(%s) 开始采集: %s", id, s.Name, s.PathPattern)
	}
}

func (m *TailerManager) StopAll() {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, w := range m.workers {
		w.stop()
	}
}

// ---------------- 单源采集 worker ----------------

type tailWorker struct {
	cfg      SourceConfig
	sender   *Sender
	registry *Registry
	newline  *regexp.Regexp
	exclude  *regexp.Regexp
	done     chan struct{}
	stopped  chan struct{}
}

func newTailWorker(cfg SourceConfig, sender *Sender, registry *Registry) *tailWorker {
	nl, err := regexp.Compile(cfg.MultilinePattern)
	if err != nil {
		nl = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}`)
	}
	var ex *regexp.Regexp
	if cfg.ExcludePattern != "" {
		ex, _ = regexp.Compile(globToRegex(cfg.ExcludePattern))
	}
	return &tailWorker{
		cfg: cfg, sender: sender, registry: registry,
		newline: nl, exclude: ex,
		done: make(chan struct{}), stopped: make(chan struct{}),
	}
}

func (w *tailWorker) sameConfig(s SourceConfig) bool { return w.cfg == s }
func (w *tailWorker) stop() {
	close(w.done)
	<-w.stopped
}

// 每个文件独立的读取状态
type fileCursor struct {
	offset  int64
	pending []string // 多行合并缓冲
	pendOff int64    // 条目起始 offset
	lineNo  int64
	lastMod time.Time
}

func (w *tailWorker) run() {
	defer close(w.stopped)
	interval := time.Duration(max(w.cfg.IntervalSeconds, 1)) * time.Second // Go 1.21+ 内置 max
	ticker := time.NewTicker(interval)
	saveTicker := time.NewTicker(saveStateEvery)
	defer ticker.Stop()
	defer saveTicker.Stop()

	cursors := map[string]*fileCursor{}

	for {
		select {
		case <-w.done:
			w.flushAll(cursors)
			w.registry.Save()
			return
		case <-saveTicker.C:
			w.registry.Save()
		case <-ticker.C:
			w.poll(cursors)
		}
	}
}

func (w *tailWorker) poll(cursors map[string]*fileCursor) {
	files := globFiles(w.cfg.PathPattern)
	alive := map[string]bool{}
	for _, f := range files {
		if w.exclude != nil && w.exclude.MatchString(f) {
			continue
		}
		alive[f] = true
		cur, ok := cursors[f]
		if !ok {
			cur = w.openNew(f)
			if cur == nil {
				continue
			}
			cursors[f] = cur
		}
		w.readNew(f, cur)
	}
	// 清理已删除文件的游标（先 flush）
	for f, cur := range cursors {
		if !alive[f] {
			w.flushEntry(f, cur)
			delete(cursors, f)
		}
	}
}

// openNew 新文件：有断点续读，无断点从末尾开始（不补采历史）。
func (w *tailWorker) openNew(path string) *fileCursor {
	info, err := os.Stat(path)
	if err != nil {
		return nil
	}
	cur := &fileCursor{lastMod: info.ModTime()}
	if st, ok := w.registry.Get(w.cfg.SourceID, path); ok {
		if st.Offset <= info.Size() {
			cur.offset = st.Offset
		}
		// offset > size 说明被 copytruncate 截断 → 从 0 重读
	} else {
		cur.offset = info.Size()
	}
	return cur
}

func (w *tailWorker) readNew(path string, cur *fileCursor) {
	info, err := os.Stat(path)
	if err != nil {
		return
	}
	// 轮转检测：文件变小 = copytruncate；rename+create 由 glob 发现新路径自然处理
	if info.Size() < cur.offset {
		log.Printf("检测到截断轮转: %s，从头重读", path)
		w.flushEntry(path, cur)
		cur.offset = 0
	}
	if info.Size() == cur.offset {
		// 无新内容：静默超时也 flush 未完结的多行
		if len(cur.pending) > 0 && time.Since(cur.lastMod) > entryFlushQuiet {
			w.flushEntry(path, cur)
		}
		return
	}

	fh, err := os.Open(path)
	if err != nil {
		return
	}
	defer fh.Close()
	if _, err := fh.Seek(cur.offset, io.SeekStart); err != nil {
		return
	}

	reader := bufio.NewReader(fh)
	for {
		line, err := reader.ReadString('\n')
		complete := strings.HasSuffix(line, "\n")
		if len(line) > 0 && complete {
			// 只处理完整行；未以 \n 结尾的半行留到下轮（offset 不前进，自动重读）
			lineLen := int64(len(line))
			line = strings.TrimRight(decodeText([]byte(line), w.cfg.Encoding), "\r\n")
			cur.lineNo++
			if w.newline.MatchString(line) || len(cur.pending) >= maxMultilineLines {
				w.flushEntry(path, cur)
				cur.pendOff = cur.offset
			}
			cur.pending = append(cur.pending, line)
			cur.offset += lineLen
			w.registry.Set(w.cfg.SourceID, path, fileState{Offset: cur.offset, Inode: path})
		}
		if err != nil {
			break
		}
	}
	cur.lastMod = time.Now()
}

func (w *tailWorker) flushEntry(path string, cur *fileCursor) {
	if len(cur.pending) == 0 {
		return
	}
	content := strings.Join(cur.pending, "\n")
	w.sender.Enqueue(w.cfg.SourceID, path, LogEvent{
		File: path, Offset: cur.pendOff, LineNo: cur.lineNo,
		Content: content, OccurredAt: time.Now(),
	})
	cur.pending = nil
}

func (w *tailWorker) flushAll(cursors map[string]*fileCursor) {
	for f, cur := range cursors {
		w.flushEntry(f, cur)
	}
}

// ---------------- glob（支持 * 与 **） ----------------

func globFiles(pattern string) []string {
	if !strings.Contains(pattern, "**") {
		matches, _ := filepath.Glob(pattern)
		return matches
	}
	// ** 递归：取 ** 前的静态前缀作为遍历根
	idx := strings.Index(pattern, "**")
	root := filepath.Dir(pattern[:idx])
	if root == "" || root == "." {
		root = string(filepath.Separator)
	}
	re := regexp.MustCompile(globToRegex(pattern))
	var out []string
	_ = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		if re.MatchString(filepath.ToSlash(path)) {
			out = append(out, path)
		}
		return nil
	})
	return out
}

// globToRegex 把 glob（*、**、?）转正则（用于 ** 匹配与排除规则）。
func globToRegex(glob string) string {
	glob = filepath.ToSlash(glob)
	var b strings.Builder
	b.WriteString("^")
	for i := 0; i < len(glob); i++ {
		c := glob[i]
		switch c {
		case '*':
			if i+1 < len(glob) && glob[i+1] == '*' {
				b.WriteString(".*")
				i++
			} else {
				b.WriteString("[^/]*")
			}
		case '?':
			b.WriteString("[^/]")
		case '.', '+', '(', ')', '[', ']', '{', '}', '^', '$', '|', '\\':
			b.WriteByte('\\')
			b.WriteByte(c)
		default:
			b.WriteByte(c)
		}
	}
	b.WriteString("$")
	return b.String()
}

// ---------------- 编码 ----------------

func decodeText(raw []byte, encoding string) string {
	if strings.EqualFold(encoding, "GBK") {
		return decodeGBK(raw)
	}
	return string(raw)
}
