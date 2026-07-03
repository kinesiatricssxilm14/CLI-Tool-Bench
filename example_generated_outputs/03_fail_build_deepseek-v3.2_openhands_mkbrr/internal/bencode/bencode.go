package bencode

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"sort"
	"strconv"
)

var (
	ErrInvalidFormat = errors.New("invalid bencode format")
	ErrTypeMismatch  = errors.New("type mismatch")
)

type Value interface{}

func Decode(r io.Reader) (Value, error) {
	return decodeValue(r)
}

func decodeValue(r io.Reader) (Value, error) {
	var buf [1]byte
	_, err := io.ReadFull(r, buf[:])
	if err != nil {
		return nil, err
	}

	switch buf[0] {
	case 'i':
		return decodeInt(r)
	case 'l':
		return decodeList(r)
	case 'd':
		return decodeDict(r)
	default:
		if buf[0] >= '0' && buf[0] <= '9':
			return decodeString(r, buf[0])
		}
		return nil, ErrInvalidFormat
}

func decodeInt(r io.Reader) (int64, error) {
	var buf bytes.Buffer
	for {
		var b [1]byte
		_, err := io.ReadFull(r, b[:])
		if err != nil {
			return 0, err
		}
		if b[0] == 'e' {
			break
		}
		buf.WriteByte(b[0])
	}
	return strconv.ParseInt(buf.String(), 10, 64)
}

func decodeString(r io.Reader, first byte) (string, error) {
	var lengthBuf bytes.Buffer
	lengthBuf.WriteByte(first)

	for {
		var b [1]byte
		_, err := io.ReadFull(r, b[:])
		if err != nil {
			return "", err
		}
		if b[0] == ':' {
			break
		}
		if b[0] < '0' || b[0] > '9' {
			return "", ErrInvalidFormat
		}
		lengthBuf.WriteByte(b[0])
	}

	length, err := strconv.ParseInt(lengthBuf.String(), 10, 64)
	if err != nil {
		return "", err
	}
	if length < 0 {
		return "", ErrInvalidFormat
	}

	buf := make([]byte, length)
	_, err = io.ReadFull(r, buf)
	if err != nil {
		return "", err
	}
	return string(buf), nil
}

func decodeList(r io.Reader) ([]Value, error) {
	var list []Value
	for {
		var b [1]byte
		_, err := io.ReadFull(r, b[:])
		if err != nil {
			return nil, err
		}
		if b[0] == 'e' {
			break
		}
		val, err := decodeValue(io.MultiReader(bytes.NewReader(b[:]), r))
		if err != nil {
			return nil, err
		}
		list = append(list, val)
	}
	return list, nil
}

func decodeDict(r io.Reader) (map[string]Value, error) {
	dict := make(map[string]Value)
	for {
		var b [1]byte
		_, err := io.ReadFull(r, b[:])
		if err != nil {
			return nil, err
		}
		if b[0] == 'e' {
			break
		}
		key, err := decodeValue(io.MultiReader(bytes.NewReader(b[:]), r))
		if err != nil {
			return nil, err
		}
		keyStr, ok := key.(string)
		if !ok {
			return nil, ErrTypeMismatch
		}

		val, err := decodeValue(r)
		if err != nil {
			return nil, err
		}
		dict[keyStr] = val
	}
	return dict, nil
}

func Encode(w io.Writer, v Value) error {
	switch val := v.(type) {
	case int64:
		return encodeInt(w, val)
	case int:
		return encodeInt(w, int64(val))
	case string:
		return encodeString(w, val)
	case []byte:
		return encodeString(w, string(val))
	case []Value:
		return encodeList(w, val)
	case map[string]Value:
		return encodeDict(w, val)
	default:
		return fmt.Errorf("unsupported type: %T", v)
	}
}

func encodeInt(w io.Writer, i int64) error {
	_, err := fmt.Fprintf(w, "i%de", i)
	return err
}

func encodeString(w io.Writer, s string) error {
	_, err := fmt.Fprintf(w, "%d:%s", len(s), s)
	return err
}

func encodeList(w io.Writer, list []Value) error {
	if _, err := w.Write([]byte{'l'}); err != nil {
		return err
	}
	for _, item := range list {
		if err := Encode(w, item); err != nil {
			return err
		}
	}
	if _, err := w.Write([]byte{'e'}); err != nil {
		return err
	}
	return nil
}

func encodeDict(w io.Writer, dict map[string]Value) error {
	if _, err := w.Write([]byte{'d'}); err != nil {
		return err
	}

	keys := make([]string, 0, len(dict))
	for k := range dict {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for _, k := range keys {
		if err := encodeString(w, k); err != nil {
			return err
		}
		if err := Encode(w, dict[k]); err != nil {
			return err
		}
	}
	if _, err := w.Write([]byte{'e'}); err != nil {
		return err
	}
	return nil
}

func Marshal(v Value) ([]byte, error) {
	var buf bytes.Buffer
	if err := Encode(&buf, v); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func Unmarshal(data []byte) (Value, error) {
	return Decode(bytes.NewReader(data))
}