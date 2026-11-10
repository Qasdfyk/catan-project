package main

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
)

// fetchRecord downloads the record the backend saved when the game ended
// (docs/game-record.md). Numbers stay json.Number, so nothing is rounded on
// the way through.
func fetchRecord(ctx context.Context, api, roomID string) (map[string]any, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("%s/api/rooms/%s/record", api, roomID), nil)
	if err != nil {
		return nil, err
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("record of %s: %d", roomID, response.StatusCode)
	}
	decoder := json.NewDecoder(response.Body)
	decoder.UseNumber()
	var record map[string]any
	if err := decoder.Decode(&record); err != nil {
		return nil, fmt.Errorf("record of %s: %w", roomID, err)
	}
	return record, nil
}

// markTournament says what the backend could not know: the tournament joins
// every seat as a guest, so the record calls them humans.
func markTournament(record map[string]any, levels []string) error {
	players, ok := record["players"].([]any)
	if !ok || len(players) != len(levels) {
		return errors.New("record has the wrong players")
	}
	for seat, entry := range players {
		player, ok := entry.(map[string]any)
		if !ok {
			return errors.New("record has the wrong players")
		}
		player["kind"] = "bot"
		player["bot_level"] = levels[seat]
	}
	record["source"] = "tournament"
	return nil
}

// saveRecord writes the record gzipped, like the backend does, under a name
// that sorts by game number. It writes a temporary file and renames it, so
// half a record never sits under the final name.
func saveRecord(dir string, game int, roomID string, record map[string]any) (err error) {
	path := filepath.Join(dir, fmt.Sprintf("game-%05d-%s.json.gz", game, roomID))
	file, err := os.CreateTemp(dir, ".record-*")
	if err != nil {
		return err
	}
	defer func() {
		if err != nil {
			os.Remove(file.Name())
		}
	}()
	// CreateTemp makes the file private; records are meant to be shared
	if err = file.Chmod(0o644); err != nil {
		file.Close()
		return err
	}
	zipped := gzip.NewWriter(file)
	if err = json.NewEncoder(zipped).Encode(record); err != nil {
		file.Close()
		return err
	}
	if err = zipped.Close(); err != nil {
		file.Close()
		return err
	}
	// On disk before the rename, so a power cut cannot leave an empty record
	if err = file.Sync(); err != nil {
		file.Close()
		return err
	}
	if err = file.Close(); err != nil {
		return err
	}
	return os.Rename(file.Name(), path)
}

// keepRecord downloads, marks and saves the record of one finished game.
func keepRecord(ctx context.Context, cfg config, game int, roomID string, levels []string) error {
	record, err := fetchRecord(ctx, cfg.api, roomID)
	if err != nil {
		return err
	}
	if err := markTournament(record, levels); err != nil {
		return err
	}
	return saveRecord(cfg.records, game, roomID, record)
}
