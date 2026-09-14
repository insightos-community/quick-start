// Copyright 2026 InsightOS
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// semantic-web-gateway serves the production SPA and proxies same-origin API/WS.
package main

import (
	"context"
	"errors"
	"flag"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"path"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// Windows builds include stop_windows.go, which registers the native stop IPC.
// Keeping the Unix default here preserves existing single-file build recipes.
var notifyStop = func() (context.Context, context.CancelFunc, error) {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	return ctx, cancel, nil
}

func handler(root, api, ws string) http.Handler {
	mux := http.NewServeMux()
	for prefix, target := range map[string]string{"/api/": api, "/ws": ws} {
		u, err := url.Parse(target)
		if err != nil {
			panic(err)
		}
		proxy := httputil.NewSingleHostReverseProxy(u)
		proxy.FlushInterval = -1 // Preserve streaming responses and SSE.
		mux.Handle(prefix, proxy)
		if prefix == "/ws" {
			mux.Handle("/ws/", proxy)
		}
	}
	files := http.FileServer(http.Dir(root))
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		if r.Method != "GET" && r.Method != "HEAD" {
			http.Error(w, "method not allowed", 405)
			return
		}
		// URL paths always use slashes. Reject Windows separators and NTFS stream
		// syntax before passing the name to the host filesystem.
		if strings.ContainsAny(r.URL.Path, "\\:") {
			http.NotFound(w, r)
			return
		}
		clean := path.Clean("/" + r.URL.Path)
		for _, part := range strings.Split(clean, "/") {
			if strings.HasPrefix(part, ".") {
				http.NotFound(w, r)
				return
			}
		}
		info, err := os.Stat(filepath.Join(root, filepath.FromSlash(strings.TrimPrefix(clean, "/"))))
		if err == nil && !info.IsDir() {
			files.ServeHTTP(w, r)
			return
		}
		if filepath.Ext(clean) != "" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Cache-Control", "no-cache")
		http.ServeFile(w, r, filepath.Join(root, "index.html"))
	})
	return mux
}

func main() {
	addr := flag.String("listen", "127.0.0.1:3000", "Web listen address")
	root := flag.String("root", "web", "Production static directory")
	api := flag.String("api", "http://127.0.0.1:8034", "Server HTTP URL")
	ws := flag.String("ws", "http://127.0.0.1:8035", "Server WebSocket URL")
	flag.Parse()
	s := &http.Server{Addr: *addr, Handler: handler(*root, *api, *ws), ReadHeaderTimeout: 10 * time.Second}
	ctx, cancel, err := notifyStop()
	if err != nil {
		log.Fatal(err)
	}
	defer cancel()
	log.Printf("Semantic Web listening on %s", *addr)
	done := make(chan error, 1)
	go func() { done <- s.ListenAndServe() }()
	select {
	case err = <-done:
		if !errors.Is(err, http.ErrServerClosed) {
			log.Fatal(err)
		}
	case <-ctx.Done():
		shutdown, release := context.WithTimeout(context.Background(), 10*time.Second)
		defer release()
		if err = s.Shutdown(shutdown); err != nil {
			log.Fatal(err)
		}
	}
}
