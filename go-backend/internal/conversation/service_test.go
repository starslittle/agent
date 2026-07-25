package conversation

import (
	"strings"
	"testing"
)

func TestBuildTitle(t *testing.T) {
	if got := BuildTitle("  帮我\n分析   Go 会话架构  "); got != "帮我 分析 Go 会话架构" {
		t.Fatalf("BuildTitle() = %q", got)
	}
	long := strings.Repeat("会", 40)
	got := BuildTitle(long)
	if len([]rune(got)) != 33 || !strings.HasSuffix(got, "…") {
		t.Fatalf("long BuildTitle() = %q", got)
	}
	if got := BuildTitle("   "); got != DefaultTitle {
		t.Fatalf("empty BuildTitle() = %q", got)
	}
}
