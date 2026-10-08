// LogSentinel Agent：内网主机主动上报日志事件到中心服务端。
//
// 用法：
//   logsentinel-agent -server http://10.99.99.152:6064 -key agt_xxx -token <token>
//
// 全部依赖仅标准库 + golang.org/x/text（GBK 解码），CGO_ENABLED=0 可交叉编译单文件。
package main

import (
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

const Version = "1.0.0"

func main() {
	server := flag.String("server", "", "中心服务地址，如 http://10.99.99.152:6064")
	key := flag.String("key", "", "Agent Key（管理端创建时生成）")
	token := flag.String("token", "", "Agent Token（管理端创建时展示）")
	stateFile := flag.String("state", "agent-state.json", "offset 断点持久化文件")
	flag.Parse()

	if *server == "" || *key == "" || *token == "" {
		log.Fatal("必须提供 -server -key -token 参数")
	}

	hostname, _ := os.Hostname()
	client := &APIClient{Server: *server, Key: *key, Token: *token, HTTP: &http.Client{Timeout: 15 * time.Second}}
	registry := NewRegistry(*stateFile)
	sender := NewSender(client)

	// 1. 注册
	reg, err := client.Register(hostname, localIP())
	if err != nil {
		log.Fatalf("注册失败: %v（请检查 server 地址 / key / token）", err)
	}
	log.Printf("注册成功: agent_id=%d 心跳间隔=%ds", reg.AgentID, reg.HeartbeatInterval)

	// 2. 启动发送器（批量 + 背压）
	sender.Start()

	// 3. 首次拉取配置并启动采集
	tailers := NewTailerManager(sender, registry)
	syncConfig(client, tailers)

	// 4. 心跳循环：保活 + 配置版本检查（热加载）+ 扫描下发
	hbInterval := time.Duration(max(reg.HeartbeatInterval, 10)) * time.Second
	lastVersion := reg.ConfigVersion
	ticker := time.NewTicker(hbInterval)
	defer ticker.Stop()

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)

	for {
		select {
		case <-sig:
			log.Println("收到退出信号，保存断点...")
			tailers.StopAll()
			registry.Save()
			return
		case <-ticker.C:
			hb, err := client.Heartbeat(sender.SentCount(), sender.QueueSize())
			if err != nil {
				log.Printf("心跳失败: %v", err)
				continue
			}
			if hb.ConfigVersion != lastVersion {
				log.Printf("配置变更 %d -> %d，热加载", lastVersion, hb.ConfigVersion)
				syncConfig(client, tailers)
				lastVersion = hb.ConfigVersion
			}
			if hb.ScanRequest != "" {
				go func(dir string) {
					files := ScanDir(dir)
					if err := client.ScanReport(dir, files); err != nil {
						log.Printf("扫描上报失败: %v", err)
					} else {
						log.Printf("扫描完成: %s 共 %d 个文件", dir, len(files))
					}
				}(hb.ScanRequest)
			}
		}
	}
}

func syncConfig(client *APIClient, tailers *TailerManager) {
	cfg, err := client.FetchConfig()
	if err != nil {
		log.Printf("拉取配置失败: %v", err)
		return
	}
	tailers.Sync(cfg.Sources)
	log.Printf("配置同步完成: %d 个日志源", len(cfg.Sources))
}

// localIP 返回本机出口 IPv4（UDP dial 不实际发包，仅选路由；失败则遍历网卡）。
func localIP() string {
	if conn, err := net.Dial("udp", "192.0.2.1:80"); err == nil {
		defer conn.Close()
		return conn.LocalAddr().(*net.UDPAddr).IP.String()
	}
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return ""
	}
	for _, a := range addrs {
		if ipnet, ok := a.(*net.IPNet); ok && !ipnet.IP.IsLoopback() && ipnet.IP.To4() != nil {
			return ipnet.IP.String()
		}
	}
	return ""
}
