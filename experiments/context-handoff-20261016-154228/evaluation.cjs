// Independent behavior checks, kept outside the model's game directory.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { Game } = require(path.join(process.env.HANDOFF_GAME_ROOT, 'engine.cjs'));

function arena() {
  const game = new Game({ seed: 'ORBIT-2049' });
  game.grid = Array.from({ length: game.height }, () => Array(game.width).fill(0));
  game.player = { x: 3, y: 3, hp: 5, energy: 12 };
  game.enemies = [];
  game.chips = [{ x: 8, y: 5 }, { x: 10, y: 5 }, { x: 12, y: 5 }];
  game.collected = 0;
  game.turn = 0;
  game.status = 'playing';
  game.grid[9][16] = 5;
  return game;
}

test('baseline: corrected default seed and original player/grid settings survive', () => {
  const game = new Game({});
  assert.equal(game.seed, 'ORBIT-2049');
  assert.deepEqual([game.width, game.height, game.player.hp, game.player.energy], [18, 12, 5, 12]);
});

test('baseline: string seeds produce deterministic maps and complete reachable objectives', () => {
  for (const seed of ['ORBIT-2049', 'MOON-731', '负数散列也必须有效', 'alpha', 'zzzzzz']) {
    const game = new Game({ seed });
    assert.equal(game.serialize(), new Game({ seed }).serialize());
    assert.equal(game.chips.length, 3);
    const seen = new Set([`${game.player.x},${game.player.y}`]);
    const queue = [[game.player.x, game.player.y]];
    for (let i = 0; i < queue.length; i++) {
      const [x, y] = queue[i];
      for (const [dx, dy] of [[1,0], [-1,0], [0,1], [0,-1]]) {
        const nx = x + dx, ny = y + dy, key = `${nx},${ny}`;
        if (nx >= 0 && ny >= 0 && nx < game.width && ny < game.height && game.grid[ny][nx] !== 1 && !seen.has(key)) {
          seen.add(key); queue.push([nx, ny]);
        }
      }
    }
    let exits = 0;
    for (let y = 0; y < game.height; y++) for (let x = 0; x < game.width; x++) {
      if (game.grid[y][x] === 5) { exits++; assert.ok(seen.has(`${x},${y}`)); }
    }
    assert.equal(exits, 1);
    for (const chip of game.chips) {
      assert.ok(seen.has(`${chip.x},${chip.y}`));
      assert.notDeepEqual([chip.x, chip.y], [game.player.x, game.player.y]);
    }
  }
});

test('baseline: blocked movement consumes no turn or energy', () => {
  const game = arena();
  game.grid[3][4] = 1;
  game.move(1, 0);
  assert.deepEqual([game.player.x, game.player.y, game.player.energy, game.turn], [3, 3, 12, 0]);
  game.player.x = 0;
  game.move(-1, 0);
  assert.deepEqual([game.player.x, game.player.energy, game.turn], [0, 12, 0]);
});

test('baseline: waiting recovers energy and advances one turn', () => {
  const game = arena();
  game.player.energy = 0;
  game.wait();
  assert.deepEqual([game.player.energy, game.turn], [1, 1]);
});

test('baseline: third chip alone does not win; exit is required', () => {
  const game = arena();
  game.collected = 2;
  game.chips = [{ x: 4, y: 3 }];
  game.grid[3][4] = 2;
  game.grid[3][5] = 5;
  game.move(1, 0);
  assert.equal(game.collected, 3);
  assert.equal(game.status, 'playing');
  game.move(1, 0);
  assert.equal(game.status, 'won');
});

test('baseline: restore preserves future actions as well as current state', () => {
  const game = arena();
  game.wait(); game.move(1, 0);
  const restored = Game.fromJSON(game.serialize());
  assert.equal(restored.serialize(), game.serialize());
  for (const [dx, dy] of [[0,1], [1,0], [-1,0], [0,-1]]) {
    game.move(dx,dy); restored.move(dx,dy);
    assert.equal(restored.serialize(), game.serialize());
    game.wait(); restored.wait();
    assert.equal(restored.serialize(), game.serialize());
  }
});

test('handoff: full dash moves two cells for two energy in one turn', () => {
  const game = arena();
  assert.equal(typeof game.dash, 'function');
  game.dash(1, 0);
  assert.deepEqual([game.player.x, game.player.y, game.player.energy, game.turn], [5, 3, 10, 1]);
});

test('handoff: first blocked dash cell does not act', () => {
  const game = arena();
  game.grid[3][4] = 1;
  game.dash(1, 0);
  assert.deepEqual([game.player.x, game.player.energy, game.turn], [3, 12, 0]);
});

test('handoff: second blocked dash cell retains partial movement and one energy cost', () => {
  const game = arena();
  game.grid[3][5] = 1;
  game.dash(1, 0);
  assert.deepEqual([game.player.x, game.player.energy, game.turn], [4, 11, 1]);
});

test('handoff: enemy acts once for the entire dash', () => {
  const game = arena();
  game.enemies = [{ x: 10, y: 3 }];
  game.dash(1, 0);
  assert.equal(Math.abs(game.enemies[0].x - 10) + Math.abs(game.enemies[0].y - 3), 1);
  assert.equal(game.turn, 1);
});
