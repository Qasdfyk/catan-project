package server

import "encoding/json"

// Messages from the browser.
type clientMessage struct {
	Type      string          `json:"type"`
	RoomID    string          `json:"room_id,omitempty"`
	Token     string          `json:"token,omitempty"`
	RequestID int64           `json:"request_id,omitempty"`
	Action    string          `json:"action,omitempty"`
	Payload   json.RawMessage `json:"payload,omitempty"`
}

// Messages to the browser.
type stateMessage struct {
	Type    string          `json:"type"`
	Public  json.RawMessage `json:"public"`
	Private json.RawMessage `json:"private"`
}

type presenceMessage struct {
	Type   string `json:"type"`
	Online []int  `json:"online"`
}

type ackMessage struct {
	Type      string `json:"type"`
	RequestID int64  `json:"request_id"`
}

type errorMessage struct {
	Type      string `json:"type"`
	RequestID int64  `json:"request_id,omitempty"`
	Message   string `json:"message"`
	Fatal     bool   `json:"fatal,omitempty"`
}

// RoomEvent is published by the backend after every change to a room. Private
// holds one opaque document per seat; the gateway never looks inside.
type RoomEvent struct {
	RoomID  string                     `json:"room_id"`
	Public  json.RawMessage            `json:"public"`
	Private map[string]json.RawMessage `json:"private"`
}
