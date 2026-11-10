package main

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

const sampleRecord = `{"format":"catan-game-record","version":1,"source":"platform","game_id":"r1",
"players":[{"seat":0,"name":"hard 0","kind":"human","bot_level":null},{"seat":1,"name":"easy 1","kind":"human","bot_level":null}],
"events":[{"turn":12345678901234567,"seat":1,"action":"roll_dice","payload":{},"outcome":{"dice":[3,4]}}]}`

func backend(t *testing.T) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/rooms/r1/record":
			w.Write([]byte(sampleRecord))
		case "/api/rooms/running/record":
			w.WriteHeader(http.StatusConflict)
		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(server.Close)
	return server
}

func readGzipJSON(t *testing.T, path string) map[string]any {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	zipped, err := gzip.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(zipped)
	decoder.UseNumber()
	var record map[string]any
	if err := decoder.Decode(&record); err != nil {
		t.Fatal(err)
	}
	return record
}

func TestKeepRecordMarksTheBots(t *testing.T) {
	dir := t.TempDir()
	cfg := config{api: backend(t).URL, records: dir}

	if err := keepRecord(context.Background(), cfg, 7, "r1", []string{"hard", "easy"}); err != nil {
		t.Fatal(err)
	}

	record := readGzipJSON(t, filepath.Join(dir, "game-00007-r1.json.gz"))
	if record["source"] != "tournament" {
		t.Errorf("source = %v", record["source"])
	}
	for seat, want := range []string{"hard", "easy"} {
		player := record["players"].([]any)[seat].(map[string]any)
		if player["kind"] != "bot" || player["bot_level"] != want {
			t.Errorf("seat %d = %v", seat, player)
		}
	}
	// Large numbers would lose digits as float64
	turn := record["events"].([]any)[0].(map[string]any)["turn"]
	if turn != json.Number("12345678901234567") {
		t.Errorf("turn = %v", turn)
	}
	entries, _ := os.ReadDir(dir)
	if len(entries) != 1 {
		t.Errorf("left %d files, want only the record", len(entries))
	}
}

func TestKeepRecordFailsWithoutSaving(t *testing.T) {
	dir := t.TempDir()
	cfg := config{api: backend(t).URL, records: dir}

	if err := keepRecord(context.Background(), cfg, 1, "running", []string{"hard", "easy"}); err == nil {
		t.Error("a game without a record was saved")
	}
	if err := keepRecord(context.Background(), cfg, 1, "r1", []string{"hard"}); err == nil {
		t.Error("a record with other seats was saved")
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 0 {
		t.Errorf("left %d files", len(entries))
	}
}
