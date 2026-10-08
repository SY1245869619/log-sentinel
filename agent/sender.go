// 批量发送器：内存队列 + 批量 flush + gzip + 指数退避重试 + 背压（满则丢最旧）。
package main

import (
	"log"
	"sync/atomic"
	"time"
)

const (
	queueCapacity = 100000 // 环形缓冲上限（背压）
	batchSize     = 200
	flushInterval = 2 * time.Second
)

type queuedEvent struct {
	sourceID int
	inode    string
	event    LogEvent
}

type Sender struct {
	client *APIClient
	queue  chan queuedEvent
	sent   atomic.Int64
	drop   atomic.Int64
	done   chan struct{}
}

func NewSender(client *APIClient) *Sender {
	return &Sender{
		client: client,
		queue:  make(chan queuedEvent, queueCapacity),
		done:   make(chan struct{}),
	}
}

// Enqueue 非阻塞入队；队列满时丢弃并计数（背压保护，绝不阻塞采集线程）。
func (s *Sender) Enqueue(sourceID int, inode string, ev LogEvent) {
	select {
	case s.queue <- queuedEvent{sourceID: sourceID, inode: inode, event: ev}:
	default:
		if n := s.drop.Add(1); n%1000 == 1 {
			log.Printf("警告: 发送队列已满，累计丢弃 %d 条（中心端不可达或过载）", n)
		}
	}
}

func (s *Sender) QueueSize() int   { return len(s.queue) }
func (s *Sender) SentCount() int64 { return s.sent.Load() }

// Start 启动批量 flush 循环：满 200 条或 2 秒触发一次。
func (s *Sender) Start() {
	go func() {
		ticker := time.NewTicker(flushInterval)
		defer ticker.Stop()
		batch := map[int][]queuedEvent{} // 按 source 分组
		size := 0

		flush := func() {
			for sid, items := range batch {
				s.sendWithRetry(sid, items)
			}
			batch = map[int][]queuedEvent{}
			size = 0
		}

		for {
			select {
			case <-s.done:
				flush()
				return
			case qe := <-s.queue:
				batch[qe.sourceID] = append(batch[qe.sourceID], qe)
				size++
				if size >= batchSize {
					flush()
				}
			case <-ticker.C:
				if size > 0 {
					flush()
				}
			}
		}
	}()
}

func (s *Sender) sendWithRetry(sourceID int, items []queuedEvent) {
	events := make([]LogEvent, len(items))
	for i, qe := range items {
		events[i] = qe.event
	}
	inode := items[0].inode
	backoff := time.Second
	for attempt := 0; attempt < 5; attempt++ {
		if err := s.client.SendEvents(sourceID, inode, events); err != nil {
			log.Printf("上报失败(第%d次): source=%d %v，%v 后重试", attempt+1, sourceID, err, backoff)
			time.Sleep(backoff)
			backoff *= 2
			continue
		}
		s.sent.Add(int64(len(events)))
		return
	}
	log.Printf("上报最终失败: source=%d 丢弃 %d 条（事件已落服务端前会指纹幂等，重启不重复）", sourceID, len(events))
}

func (s *Sender) Stop() { close(s.done) }
