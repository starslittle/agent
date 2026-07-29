package conversation

import (
	"testing"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

func TestResolveTerminalStatus(t *testing.T) {
	tests := []struct {
		name      string
		current   string
		requested string
		want      string
	}{
		{
			name:      "normal completion",
			current:   string(agent.StatusRunning),
			requested: string(agent.StatusCompleted),
			want:      string(agent.StatusCompleted),
		},
		{
			name:      "cancellation wins completion race",
			current:   string(agent.StatusCancelRequested),
			requested: string(agent.StatusCompleted),
			want:      string(agent.StatusCancelled),
		},
		{
			name:      "explicit cancellation stays cancelled",
			current:   string(agent.StatusCancelRequested),
			requested: string(agent.StatusCancelled),
			want:      string(agent.StatusCancelled),
		},
		{
			name:      "failure remains observable after cancellation request",
			current:   string(agent.StatusCancelRequested),
			requested: string(agent.StatusFailed),
			want:      string(agent.StatusFailed),
		},
		{
			name:      "terminal status is irreversible",
			current:   string(agent.StatusCancelled),
			requested: string(agent.StatusCompleted),
			want:      string(agent.StatusCancelled),
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := ResolveTerminalStatus(test.current, test.requested); got != test.want {
				t.Fatalf(
					"ResolveTerminalStatus(%q, %q) = %q, want %q",
					test.current,
					test.requested,
					got,
					test.want,
				)
			}
		})
	}
}
