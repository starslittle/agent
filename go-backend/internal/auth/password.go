package auth

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"golang.org/x/crypto/argon2"
)

const (
	argonMemory      = 19 * 1024
	argonIterations  = 2
	argonParallelism = 1
	argonSaltLength  = 16
	argonKeyLength   = 32
)

func HashPassword(password string) (string, error) {
	if err := ValidatePassword(password); err != nil {
		return "", err
	}
	salt := make([]byte, argonSaltLength)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("generate password salt: %w", err)
	}
	hash := argon2.IDKey(
		[]byte(password),
		salt,
		argonIterations,
		argonMemory,
		argonParallelism,
		argonKeyLength,
	)
	return fmt.Sprintf(
		"$argon2id$v=%d$m=%d,t=%d,p=%d$%s$%s",
		argon2.Version,
		argonMemory,
		argonIterations,
		argonParallelism,
		base64.RawStdEncoding.EncodeToString(salt),
		base64.RawStdEncoding.EncodeToString(hash),
	), nil
}

func VerifyPassword(encoded, password string) bool {
	parts := strings.Split(encoded, "$")
	if len(parts) != 6 || parts[1] != "argon2id" {
		return false
	}
	var version int
	if _, err := fmt.Sscanf(parts[2], "v=%d", &version); err != nil || version != argon2.Version {
		return false
	}
	params := strings.Split(parts[3], ",")
	if len(params) != 3 {
		return false
	}
	memory, okMemory := parseArgonParam(params[0], "m")
	iterations, okIterations := parseArgonParam(params[1], "t")
	parallelism, okParallelism := parseArgonParam(params[2], "p")
	if !okMemory || !okIterations || !okParallelism ||
		memory > 256*1024 || iterations > 10 || parallelism > 16 {
		return false
	}
	salt, err := base64.RawStdEncoding.DecodeString(parts[4])
	if err != nil || len(salt) < 8 {
		return false
	}
	expected, err := base64.RawStdEncoding.DecodeString(parts[5])
	if err != nil || len(expected) < 16 {
		return false
	}
	actual := argon2.IDKey(
		[]byte(password),
		salt,
		uint32(iterations),
		uint32(memory),
		uint8(parallelism),
		uint32(len(expected)),
	)
	return subtle.ConstantTimeCompare(actual, expected) == 1
}

func ValidatePassword(password string) error {
	length := len([]rune(password))
	if length < 12 {
		return errors.New("password must contain at least 12 characters")
	}
	if length > 128 {
		return errors.New("password must contain at most 128 characters")
	}
	return nil
}

func parseArgonParam(raw, name string) (uint64, bool) {
	key, value, ok := strings.Cut(raw, "=")
	if !ok || key != name {
		return 0, false
	}
	parsed, err := strconv.ParseUint(value, 10, 32)
	return parsed, err == nil && parsed > 0
}
