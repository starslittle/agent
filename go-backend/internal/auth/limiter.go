package auth

import (
	"sync"
	"time"
)

type loginWindow struct {
	count     int
	expiresAt time.Time
}

type LoginLimiter struct {
	mu       sync.Mutex
	windows  map[string]loginWindow
	max      int
	duration time.Duration
}

func NewLoginLimiter(max int, duration time.Duration) *LoginLimiter {
	return &LoginLimiter{
		windows:  make(map[string]loginWindow),
		max:      max,
		duration: duration,
	}
}

func (l *LoginLimiter) Allow(key string, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	window := l.windows[key]
	if window.expiresAt.IsZero() || !now.Before(window.expiresAt) {
		window = loginWindow{expiresAt: now.Add(l.duration)}
	}
	if window.count >= l.max {
		l.windows[key] = window
		return false
	}
	window.count++
	l.windows[key] = window
	if len(l.windows) > 10_000 {
		for candidate, item := range l.windows {
			if !now.Before(item.expiresAt) {
				delete(l.windows, candidate)
			}
		}
	}
	return true
}

func (l *LoginLimiter) Reset(key string) {
	l.mu.Lock()
	delete(l.windows, key)
	l.mu.Unlock()
}
