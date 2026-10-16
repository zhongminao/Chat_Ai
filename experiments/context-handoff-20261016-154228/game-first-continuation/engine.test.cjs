'use strict';

const { test } = require('node:test');
const assert = require('assert');

// 导入游戏引擎
const { Game } = require('./engine.cjs');

// 测试：种子复现
test('seed reproducibility', () => {
  const game1 = new Game({ seed: 'MOON-731' });
  const game2 = new Game({ seed: 'MOON-731' });

  // 检查初始状态是否一致
  assert.strictEqual(game1.player.x, game2.player.x);
  assert.strictEqual(game1.player.y, game2.player.y);
  assert.deepStrictEqual(game1.chips, game2.chips);
  assert.deepStrictEqual(game1.enemies, game2.enemies);
});

// 测试：地图可达性
test('map reachability', () => {
  const game = new Game({ seed: 'MOON-731' });

  // 检查玩家起始位置是否为空
  assert.strictEqual(game.grid[game.player.y][game.player.x], 0);

  // 检查出口是否存在
  let exitFound = false;
  for (let y = 0; y < game.height; y++) {
    for (let x = 0; x < game.width; x++) {
      if (game.grid[y][x] === 5) { // EXIT
        exitFound = true;
        break;
      }
    }
    if (exitFound) break;
  }
  assert.ok(exitFound);

  // 检查是否至少有3个芯片
  assert.ok(game.chips.length >= 3);
});

// 测试：无效移动不推进回合
test('invalid moves dont advance turn', () => {
  const game = new Game({ seed: 'MOON-731' });
  const initialTurn = game.turn;

  // 尝试无效移动（撞墙）
  const result = game.move(-1, 0); // 假设左边是墙
  assert.strictEqual(game.turn, initialTurn);
  assert.strictEqual(result, false);
});

// 测试：等待恢复能量
test('wait restores energy', () => {
  const game = new Game({ seed: 'MOON-731' });

  // 消耗能量
  game.player.energy = 0;
  game.wait();

  assert.strictEqual(game.player.energy, 1);
});

// 测试：序列化一致性
test('serialization consistency', () => {
  const originalGame = new Game({ seed: 'MOON-731' });
  const serialized = originalGame.serialize();
  const restoredGame = Game.fromJSON(serialized);

  assert.strictEqual(originalGame.player.x, restoredGame.player.x);
  assert.strictEqual(originalGame.player.y, restoredGame.player.y);
  assert.strictEqual(originalGame.player.hp, restoredGame.player.hp);
  assert.strictEqual(originalGame.player.energy, restoredGame.player.energy);
  assert.strictEqual(originalGame.collected, restoredGame.collected);
  assert.strictEqual(originalGame.turn, restoredGame.turn);
  assert.strictEqual(originalGame.status, restoredGame.status);
  assert.deepStrictEqual(originalGame.chips, restoredGame.chips);
  assert.deepStrictEqual(originalGame.enemies, restoredGame.enemies);
});

// 测试：游戏状态
test('game status', () => {
  const game = new Game({ seed: 'MOON-731' });

  // 初始状态应该是playing
  assert.strictEqual(game.status, 'playing');

  // 收集所有芯片后应该赢
  game.collected = 3;
  game.player.x = 0; // 假设出口在(0,0)
  game.player.y = 0;
  game.grid[0][0] = 5; // EXIT

  game.move(0, 0); // 移动到出口
  assert.strictEqual(game.status, 'won');
});