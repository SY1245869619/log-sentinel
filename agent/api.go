// 服务端 API 客户端：注册/心跳/配置/事件上报/扫描上报。
package main

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"runtime"
	"time"
)

type APIClient struct {
	Server string
	Key    string
	Token  string
	HTTP   *http.Client
}

type RegisterResp struct {
	AgentID           int `json:"agent_id"`
	HeartbeatInterval int `json:"heartbeat_interval"`
	ConfigVersion     int `json:"config_version"`
}

type HeartbeatResp struct {
	ConfigVersion int    `json:"config_version"`
	ScanRequest   string `json:"scan_request"`
}

type SourceConfig struct {
	SourceID         int    `json:"source_id"`
	Name             string `json:"name"`
	PathPattern      string `json:"path_pattern"`
	ExcludePattern   string `json:"exclude_pattern"`
	Encoding         string `json:"encoding"`
	MultilinePattern string `json:"multiline_pattern"`
	IntervalSeconds  int    `json:"interval_seconds"`
}

type ConfigResp struct {
	ConfigVersion int            `json:"config_version"`
	Sources       []SourceConfig `json:"sources"`
}

type LogEvent struct {
	File       string    `json:"file"`
	Offset     int64     `json:"offset"`
	LineNo     int64     `json:"line_no,omitempty"`
	Content    string    `json:"content"`
	OccurredAt time.Time `json:"occurred_at"`
}

type eventsReq struct {
	SourceID int        `json:"source_id"`
	Inode    string     `json:"inode"`
	Events   []LogEvent `json:"events"`
}

type apiResp struct {
	Code int             `json:"code"`
	Msg  string          `json:"msg"`
	Data json.RawMessage `json:"data"`
}

func (c *APIClient) do(method, path string, body []byte, gzipBody bool, out any) error {
	var reader io.Reader
	headers := map[string]string{
		"X-Agent-Key":   c.Key,
		"Authorization": "Bearer " + c.Token,
		"Content-Type":  "application/json",
	}
	if body != nil {
		if gzipBody {
			var buf bytes.Buffer
			zw := gzip.NewWriter(&buf)
			if _, err := zw.Write(body); err != nil {
				return err
			}
			zw.Close()
			reader = &buf
			headers["Content-Encoding"] = "gzip"
		} else {
			reader = bytes.NewReader(body)
		}
	}
	req, err := http.NewRequest(method, c.Server+path, reader)
	if err != nil {
		return err
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	var ar apiResp
	if err := json.Unmarshal(raw, &ar); err != nil {
		return fmt.Errorf("响应解析失败: %v body=%s", err, truncate(string(raw), 200))
	}
	if ar.Code != 0 {
		return fmt.Errorf("服务端拒绝: %s", ar.Msg)
	}
	if out != nil && len(ar.Data) > 0 {
		return json.Unmarshal(ar.Data, out)
	}
	return nil
}

func truncate(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

func (c *APIClient) Register(hostname, ip string) (*RegisterResp, error) {
	body, _ := json.Marshal(map[string]string{
		"hostname": hostname, "ip": ip,
		"os": runtime.GOOS, "arch": runtime.GOARCH, "version": Version,
	})
	var out RegisterResp
	return &out, c.do("POST", "/api/v1/agent/register", body, false, &out)
}

func (c *APIClient) Heartbeat(eventsSent int64, queueSize int) (*HeartbeatResp, error) {
	body, _ := json.Marshal(map[string]any{
		"version": Version, "events_sent": eventsSent, "queue_size": queueSize,
	})
	var out HeartbeatResp
	return &out, c.do("POST", "/api/v1/agent/heartbeat", body, false, &out)
}

func (c *APIClient) FetchConfig() (*ConfigResp, error) {
	var out ConfigResp
	return &out, c.do("GET", "/api/v1/agent/config", nil, false, &out)
}

// SendEvents 批量上报（gzip 压缩）。
func (c *APIClient) SendEvents(sourceID int, inode string, events []LogEvent) error {
	body, _ := json.Marshal(eventsReq{SourceID: sourceID, Inode: inode, Events: events})
	var out struct {
		Accepted int `json:"accepted"`
	}
	return c.do("POST", "/api/v1/agent/events", body, true, &out)
}

func (c *APIClient) ScanReport(baseDir string, files []string) error {
	body, _ := json.Marshal(map[string]any{"base_dir": baseDir, "files": files})
	return c.do("POST", "/api/v1/agent/scan/report", body, false, nil)
}
