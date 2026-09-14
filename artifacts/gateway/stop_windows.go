//go:build windows

// Copyright 2026 InsightOS
// SPDX-License-Identifier: Apache-2.0

package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"unsafe"
)

func init() { notifyStop = windowsStopContext }

func windowsStopContext() (context.Context, context.CancelFunc, error) {
	kernel := syscall.NewLazyDLL("kernel32.dll")
	closeHandle := kernel.NewProc("CloseHandle")
	var created, exited, user, cpu syscall.Filetime
	current, _, _ := kernel.NewProc("GetCurrentProcess").Call()
	ok, _, err := kernel.NewProc("GetProcessTimes").Call(current,
		uintptr(unsafe.Pointer(&created)), uintptr(unsafe.Pointer(&exited)),
		uintptr(unsafe.Pointer(&cpu)), uintptr(unsafe.Pointer(&user)))
	if ok == 0 {
		return nil, nil, err
	}
	name, err := syscall.UTF16PtrFromString(fmt.Sprintf(`Local\InsightOS.Semantic.Stop.%d.%08x%08x`,
		os.Getpid(), created.HighDateTime, created.LowDateTime))
	if err != nil {
		return nil, nil, err
	}
	event, _, createErr := kernel.NewProc("CreateEventW").Call(0, 1, 0, uintptr(unsafe.Pointer(name)))
	if event == 0 {
		return nil, nil, createErr
	}
	if createErr == syscall.ERROR_ALREADY_EXISTS {
		closeHandle.Call(event)
		return nil, nil, fmt.Errorf("stop endpoint already exists: %w", createErr)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	done := make(chan struct{})
	go func() {
		defer close(done)
		defer closeHandle.Call(event)
		wait := kernel.NewProc("WaitForSingleObject")
		for ctx.Err() == nil {
			state, _, _ := wait.Call(event, 50)
			if state != 258 { // WAIT_TIMEOUT
				cancel()
				return
			}
		}
	}()
	var once sync.Once
	return ctx, func() { once.Do(func() { cancel(); <-done }) }, nil
}
