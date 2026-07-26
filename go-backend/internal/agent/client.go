package agent

import (
	"context"
	"errors"
	"io"
)

var ErrSequenceGap = errors.New("agent event sequence gap")

type EventStream interface {
	Next() (Event, error)
	Close() error
}

type Client interface {
	Start(context.Context, RunRequest) (EventStream, error)
	Resume(context.Context, RunRequest, int64) (EventStream, error)
	Get(context.Context, string, string, string) (Snapshot, error)
	Cancel(context.Context, string, string, string) (Snapshot, error)
}

func IsStreamDone(err error) bool {
	return errors.Is(err, io.EOF)
}
