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

package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestProductionGateway(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "index.html"), []byte("semantic-spa"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "main.js"), []byte("static-js"), 0644); err != nil {
		t.Fatal(err)
	}
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("proxied:" + r.URL.Path))
	}))
	defer backend.Close()
	web := httptest.NewServer(handler(root, backend.URL, backend.URL))
	defer web.Close()
	for path, expected := range map[string]string{"/": "semantic-spa", "/projects/123": "semantic-spa", "/main.js": "static-js", "/api/v1/test": "proxied:/api/v1/test", "/ws/pilot": "proxied:/ws/pilot"} {
		r, err := http.Get(web.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		body, _ := io.ReadAll(r.Body)
		r.Body.Close()
		if r.StatusCode != 200 || string(body) != expected {
			t.Fatalf("%s: %d %s", path, r.StatusCode, body)
		}
	}
	for _, path := range []string{"/.env", "/missing.js"} {
		r, err := http.Get(web.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		r.Body.Close()
		if r.StatusCode != 404 {
			t.Fatalf("%s exposed or incorrectly served SPA", path)
		}
	}
}
