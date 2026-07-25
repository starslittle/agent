package auth

import "testing"

func TestPasswordRoundTrip(t *testing.T) {
	encoded, err := HashPassword("a sufficiently long password")
	if err != nil {
		t.Fatalf("HashPassword() error = %v", err)
	}
	if !VerifyPassword(encoded, "a sufficiently long password") {
		t.Fatal("VerifyPassword() rejected the original password")
	}
	if VerifyPassword(encoded, "a different long password") {
		t.Fatal("VerifyPassword() accepted the wrong password")
	}
}

func TestValidatePassword(t *testing.T) {
	if err := ValidatePassword("too-short"); err == nil {
		t.Fatal("ValidatePassword() accepted a short password")
	}
}
