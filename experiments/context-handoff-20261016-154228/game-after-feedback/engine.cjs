'use strict';

// 伪随机数生成器（线性同余法）
class Random {
  constructor(seed) {
    this.seed = seed;
    this.state = seed.hashCode ? seed.hashCode() : seed;
  }

  next() {
    this.state = (this.state * 1664525 + 1013904223) % Math.pow(2, 32);
    return this.state;
  }

  // 返回 [0, max)
  nextInt(max) {
    return this.next() % max;
  }

  // 返回 [min, max)
  nextRange(min, max) {
    return min + (this.next() % (max - min));
  }
}

// 地图元素类型
const TILE_TYPES = {
  EMPTY: 0,
  WALL: 1,
  CHIP: 2,
  SUPPLY: 3,
  ENEMY: 4,
  EXIT: 5
};

// 游戏主类
class Game {
  constructor({ seed = 'ORBIT-2049', width = 18, height = 12 }) {
    this.width = width;
    this.height = height;
    this.seed = seed;
    this.random = new Random(seed.hashCode ? seed.hashCode() : seed);
    
    // 游戏状态
    this.player = { x: 0, y: 0, hp: 5, energy: 12 };
    this.enemies = [];
    this.chips = [];
    this.collected = 0;
    this.turn = 0;
    this.status = 'playing';
    
    // 地图网格
    this.grid = Array(this.height).fill().map(() => Array(this.width).fill(TILE_TYPES.EMPTY));
    
    // 初始化地图
    this._generateMap();
  }

  // 生成地图（保证可达性）
  _generateMap() {
    // 先清空地图
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        this.grid[y][x] = TILE_TYPES.EMPTY;
      }
    }

    // 放置墙（随机但不完全随机）
    const wallCount = Math.floor((this.width * this.height) * 0.2);
    for (let i = 0; i < wallCount; i++) {
      let x, y;
      do {
        x = this.random.nextInt(this.width);
        y = this.random.nextInt(this.height);
      } while (this.grid[y][x] !== TILE_TYPES.EMPTY);
      this.grid[y][x] = TILE_TYPES.WALL;
    }

    // 确保玩家起始位置为空
    let startX, startY;
    do {
      startX = this.random.nextInt(this.width);
      startY = this.random.nextInt(this.height);
    } while (this.grid[startY][startX] !== TILE_TYPES.EMPTY);
    this.player.x = startX;
    this.player.y = startY;

    // 生成芯片（3个）
    for (let i = 0; i < 3; i++) {
      let x, y;
      do {
        x = this.random.nextInt(this.width);
        y = this.random.nextInt(this.height);
      } while (this.grid[y][x] !== TILE_TYPES.EMPTY);
      this.grid[y][x] = TILE_TYPES.CHIP;
      this.chips.push({ x, y });
    }

    // 生成补给
    const supplyCount = 3;
    for (let i = 0; i < supplyCount; i++) {
      let x, y;
      do {
        x = this.random.nextInt(this.width);
        y = this.random.nextInt(this.height);
      } while (this.grid[y][x] !== TILE_TYPES.EMPTY);
      this.grid[y][x] = TILE_TYPES.SUPPLY;
    }

    // 生成敌人
    const enemyCount = 4;
    for (let i = 0; i < enemyCount; i++) {
      let x, y;
      do {
        x = this.random.nextInt(this.width);
        y = this.random.nextInt(this.height);
      } while (this.grid[y][x] !== TILE_TYPES.EMPTY);
      this.grid[y][x] = TILE_TYPES.ENEMY;
      this.enemies.push({ x, y });
    }

    // 生成出口
    let exitX, exitY;
    do {
      exitX = this.random.nextInt(this.width);
      exitY = this.random.nextInt(this.height);
    } while (this.grid[exitY][exitX] !== TILE_TYPES.EMPTY);
    this.grid[exitY][exitX] = TILE_TYPES.EXIT;

    // 简单检查可达性（不保证完全连通，但基本满足）
    if (!this._isReachable(this.player.x, this.player.y, exitX, exitY)) {
      // 重置地图生成逻辑（简化处理）
      this._generateMap();
    }
    
    // 检查芯片是否在可达位置
    for (const chip of this.chips) {
      if (!this._isReachable(this.player.x, this.player.y, chip.x, chip.y)) {
        // 重置地图生成逻辑（简化处理）
        this._generateMap();
        return;
      }
    }
    
    // 检查出口是否可达
    if (!this._isReachable(this.player.x, this.player.y, exitX, exitY)) {
      // 重置地图生成逻辑（简化处理）
      this._generateMap();
      return;
    }
  }

  // 简单的可达性检查（广度优先搜索）
  _isReachable(startX, startY, endX, endY) {
    const visited = Array(this.height).fill().map(() => Array(this.width).fill(false));
    const queue = [[startX, startY]];
    visited[startY][startX] = true;

    const directions = [[0, 1], [1, 0], [0, -1], [-1, 0]];

    while (queue.length > 0) {
      const [x, y] = queue.shift();
      
      if (x === endX && y === endY) {
        return true;
      }

      for (const [dx, dy] of directions) {
        const nx = x + dx;
        const ny = y + dy;

        if (nx >= 0 && nx < this.width && ny >= 0 && ny < this.height &&
            !visited[ny][nx] && this.grid[ny][nx] !== TILE_TYPES.WALL) {
          visited[ny][nx] = true;
          queue.push([nx, ny]);
        }
      }
    }

    return false;
  }

  // 移动玩家
  move(dx, dy) {
    if (this.status !== 'playing') return false;

    const newX = this.player.x + dx;
    const newY = this.player.y + dy;

    // 检查边界
    if (newX < 0 || newX >= this.width || newY < 0 || newY >= this.height) {
      return false;
    }

    // 检查是否是墙
    if (this.grid[newY][newX] === TILE_TYPES.WALL) {
      return false;
    }

    // 扣除能量
    if (this.player.energy <= 0) {
      return false;
    }
    this.player.energy--;

    // 移动玩家
    this.player.x = newX;
    this.player.y = newY;

    // 检查是否收集芯片
    const chipIndex = this.chips.findIndex(chip => chip.x === newX && chip.y === newY);
    if (chipIndex !== -1) {
      this.chips.splice(chipIndex, 1);
      this.collected++;
    }

    // 检查是否获得补给
    if (this.grid[newY][newX] === TILE_TYPES.SUPPLY) {
      this.player.energy += 5;
      this.grid[newY][newX] = TILE_TYPES.EMPTY;
    }

    // 检查是否到达出口
    if (this.grid[newY][newX] === TILE_TYPES.EXIT) {
      if (this.collected >= 3) {
        this.status = 'won';
      }
    }

    // 敌人行动
    this._enemyAction();

    // 增加回合数
    this.turn++;
    
    return true;
  }

  // 等待恢复能量
  wait() {
    if (this.status !== 'playing') return false;

    this.player.energy = Math.min(12, this.player.energy + 1);
    this._enemyAction();
    this.turn++;
    return true;
  }

  // 敌人行动
  _enemyAction() {
    const damageDealt = new Set(); // 避免同一回合重复伤害

    for (let i = 0; i < this.enemies.length; i++) {
      const enemy = this.enemies[i];
      
      // 简单的AI：向玩家移动
      const dx = this.player.x - enemy.x;
      const dy = this.player.y - enemy.y;

      let moveX = 0;
      let moveY = 0;

      if (Math.abs(dx) > Math.abs(dy)) {
        moveX = dx > 0 ? 1 : -1;
      } else {
        moveY = dy > 0 ? 1 : -1;
      }

      const newX = enemy.x + moveX;
      const newY = enemy.y + moveY;

      // 检查边界和墙
      if (newX >= 0 && newX < this.width && newY >= 0 && newY < this.height &&
          this.grid[newY][newX] !== TILE_TYPES.WALL) {
        // 检查是否撞到玩家
        if (newX === this.player.x && newY === this.player.y) {
          if (!damageDealt.has(`${newX},${newY}`)) {
            damageDealt.add(`${newX},${newY}`);
            this.player.hp--;
            if (this.player.hp <= 0) {
              this.status = 'lost';
            }
          }
        } else {
          // 移动敌人
          enemy.x = newX;
          enemy.y = newY;
        }
      }
    }
  }

  // 序列化游戏状态
  serialize() {
    return JSON.stringify({
      seed: this.seed,
      player: this.player,
      enemies: this.enemies,
      chips: this.chips,
      collected: this.collected,
      turn: this.turn,
      status: this.status,
      grid: this.grid,
      randomState: this.random.state
    });
  }

  // 从JSON恢复游戏状态
  static fromJSON(jsonString) {
    const data = JSON.parse(jsonString);
    
    const game = new Game({ seed: data.seed, width: data.grid[0].length, height: data.grid.length });
    game.player = data.player;
    game.enemies = data.enemies;
    game.chips = data.chips;
    game.collected = data.collected;
    game.turn = data.turn;
    game.status = data.status;
    game.grid = data.grid;
    game.random.state = data.randomState;

    return game;
  }
}

// 字符串哈希函数
String.prototype.hashCode = function() {
  let hash = 0;
  for (let i = 0; i < this.length; i++) {
    const char = this.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // 转换为32位整数
  }
  return hash;
};

// 导出模块（Node.js）
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Game };
} else {
  // 浏览器环境下的导出
  window.Game = Game;
}