package bot

import (
	"cmp"
	"math"
	"slices"
)

// corner identifies a vertex by its rounded coordinates, so the same corner
// reached from different hexes gets the same key.
type corner [2]int

func cornerOf(at point) corner {
	return corner{int(math.Round(at.x * 100)), int(math.Round(at.y * 100))}
}

// side is an edge as its two corners in a fixed order.
type side [2]corner

func sideOf(a, b corner) side {
	if cmp.Or(cmp.Compare(a[0], b[0]), cmp.Compare(a[1], b[1])) > 0 {
		a, b = b, a
	}
	return side{a, b}
}

func (p Position) side() side {
	ends := p.edgeEnds()
	return sideOf(cornerOf(ends[0]), cornerOf(ends[1]))
}

// board is the graph of corners and edges the hard level plans on.
type board struct {
	corners   []corner
	points    map[corner]point
	tiles     map[corner][]Tile
	next      map[corner][]corner
	roads     map[side]string
	buildings map[corner]Building
	ports     map[corner]string
	mine      string
}

func newBoard(view View) *board {
	game := view.Public.Game
	b := &board{
		points:    map[corner]point{},
		tiles:     map[corner][]Tile{},
		next:      map[corner][]corner{},
		roads:     map[side]string{},
		buildings: map[corner]Building{},
		ports:     map[corner]string{},
		mine:      view.Public.Players[view.Private.Seat].Color,
	}
	linked := map[side]bool{}
	for _, tile := range game.BoardTiles {
		for direction := range 6 {
			vertex := Position{tile.Hex, direction}.vertex()
			at := cornerOf(vertex)
			if _, known := b.tiles[at]; !known {
				b.corners = append(b.corners, at)
				b.points[at] = vertex
			}
			b.tiles[at] = append(b.tiles[at], tile)
			edge := Position{tile.Hex, direction}.side()
			if !linked[edge] {
				linked[edge] = true
				b.next[edge[0]] = append(b.next[edge[0]], edge[1])
				b.next[edge[1]] = append(b.next[edge[1]], edge[0])
			}
		}
	}
	// A fixed order keeps the choices repeatable
	slices.SortFunc(b.corners, func(x, y corner) int {
		return cmp.Or(cmp.Compare(x[0], y[0]), cmp.Compare(x[1], y[1]))
	})
	for _, road := range game.Roads {
		b.roads[road.side()] = road.Color
	}
	for _, building := range game.Settlements {
		b.buildings[cornerOf(building.vertex())] = building
	}
	for _, port := range game.Ports {
		for _, at := range port.Vertices {
			b.ports[cornerOf(at.vertex())] = port.Type
		}
	}
	return b
}

// free is a corner where a settlement may stand by the distance rule.
func (b *board) free(at corner) bool {
	if _, taken := b.buildings[at]; taken {
		return false
	}
	for _, near := range b.next[at] {
		if _, taken := b.buildings[near]; taken {
			return false
		}
	}
	return true
}

// blocked is a corner a road of the bot cannot pass: an opponent builds there.
func (b *board) blocked(at corner) bool {
	building, taken := b.buildings[at]
	return taken && building.Owner != b.mine
}

// network is every corner the bot can build a road from.
func (b *board) network() []corner {
	var start []corner
	for _, at := range b.corners {
		if building, ok := b.buildings[at]; ok && building.Owner == b.mine {
			start = append(start, at)
			continue
		}
		if b.blocked(at) {
			continue
		}
		for _, near := range b.next[at] {
			if b.roads[sideOf(at, near)] == b.mine {
				start = append(start, at)
				break
			}
		}
	}
	return start
}

// distances counts the new roads needed to reach each corner from the start,
// through edges nobody has built on and around opponents' buildings.
func (b *board) distances(start []corner, limit int) map[corner]int {
	dist := map[corner]int{}
	queue := []corner{}
	for _, at := range start {
		dist[at] = 0
		queue = append(queue, at)
	}
	for len(queue) > 0 {
		at := queue[0]
		queue = queue[1:]
		if dist[at] >= limit || (b.blocked(at) && dist[at] > 0) {
			continue
		}
		for _, near := range b.next[at] {
			if _, seen := dist[near]; seen {
				continue
			}
			if _, built := b.roads[sideOf(at, near)]; built {
				continue
			}
			dist[near] = dist[at] + 1
			queue = append(queue, near)
		}
	}
	return dist
}

// longestRoad is the longest trail along the bot's roads, with the extra edge
// counted as its own. Opponents' buildings break a trail.
func (b *board) longestRoad(extra *side) int {
	own := map[corner][]corner{}
	add := func(edge side) {
		own[edge[0]] = append(own[edge[0]], edge[1])
		own[edge[1]] = append(own[edge[1]], edge[0])
	}
	for _, at := range b.corners {
		for _, near := range b.next[at] {
			edge := sideOf(at, near)
			if edge[0] == at && b.roads[edge] == b.mine {
				add(edge)
			}
		}
	}
	if extra != nil {
		add(*extra)
	}
	used := map[side]bool{}
	var walk func(at corner) int
	walk = func(at corner) int {
		best := 0
		for _, near := range own[at] {
			edge := sideOf(at, near)
			if used[edge] {
				continue
			}
			used[edge] = true
			length := 1
			if !b.blocked(near) {
				length += walk(near)
			}
			used[edge] = false
			best = max(best, length)
		}
		return best
	}
	longest := 0
	for _, at := range b.corners {
		if len(own[at]) > 0 {
			longest = max(longest, walk(at))
		}
	}
	return longest
}
