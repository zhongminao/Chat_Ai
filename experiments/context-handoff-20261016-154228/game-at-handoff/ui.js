// 导入游戏引擎
const { Game } = require('./engine.cjs');

// 游戏状态
let game = null;
let canvas = null;
let ctx = null;
let tile_size = 32;
let view_radius = 3;

// 初始化游戏
function initGame(seed = 'ORBIT-2049') {
  game = new Game({ seed: seed });
  updateUI();
  drawGame();
}

// 更新UI状态显示
function updateUI() {
  if (!game) return;
  
  document.getElementById('hp').textContent = game.player.hp;
  document.getElementById('energy').textContent = game.player.energy;
  document.getElementById('chips').textContent = game.collected;
  document.getElementById('turn').textContent = game.turn;
}

// 绘制游戏画面
function drawGame() {
  if (!game || !canvas || !ctx) return;

  const width = game.width;
  const height = game.height;

  // 清除画布
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 计算视野中心
  const center_x = game.player.x;
  const center_y = game.player.y;

  // 绘制地图
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      // 检查是否在视野范围内
      const dx = Math.abs(x - center_x);
      const dy = Math.abs(y - center_y);
      const in_view = (dx <= view_radius && dy <= view_radius);

      // 绘制格子
      const screen_x = (x - center_x + view_radius) * tile_size;
      const screen_y = (y - center_y + view_radius) * tile_size;

      if (in_view) {
        // 在视野内绘制
        const tile_type = game.grid[y][x];
        switch (tile_type) {
          case 0: // EMPTY
            ctx.fillStyle = '#121226';
            break;
          case 1: // WALL
            ctx.fillStyle = '#4a4a6a';
            break;
          case 2: // CHIP
            ctx.fillStyle = '#4fc3f7';
            break;
          case 3: // SUPPLY
            ctx.fillStyle = '#ff9800';
            break;
          case 4: // ENEMY
            ctx.fillStyle = '#f44336';
            break;
          case 5: // EXIT
            ctx.fillStyle = '#8bc34a';
            break;
        }
        ctx.fillRect(screen_x, screen_y, tile_size, tile_size);
      } else {
        // 在视野外绘制迷雾
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(screen_x, screen_y, tile_size, tile_size);
      }
    }
  }

  // 绘制玩家
  const player_screen_x = (game.player.x - center_x + view_radius) * tile_size;
  const player_screen_y = (game.player.y - center_y + view_radius) * tile_size;
  ctx.fillStyle = '#2196f3';
  ctx.fillRect(player_screen_x, player_screen_y, tile_size, tile_size);
}

// 处理移动
function movePlayer(dx, dy) {
  if (!game || game.status !== 'playing') return false;

  const success = game.move(dx, dy);
  updateUI();
  drawGame();
  return success;
}

// 等待动作
function waitAction() {
  if (!game || game.status !== 'playing') return false;

  game.wait();
  updateUI();
  drawGame();
  return true;
}

// 导出回放
function exportReplay() {
  if (!game) return;
  
  const replayData = {
    seed: game.seed,
    actions: []
  };
  
  // 这里应该记录所有动作，为简化起见我们只记录当前状态
  alert('导出功能需要完整实现动作序列记录，当前仅显示提示');
}

// 导入回放
function importReplay() {
  alert('导入功能需要完整实现，当前仅显示提示');
}

// 保存到槽位
function saveToSlot(slot) {
  if (!game) return;
  
  try {
    const data = game.serialize();
    localStorage.setItem(`game_save_${slot}`, data);
    alert(`已保存到槽位${slot}`);
  } catch (e) {
    alert('保存失败');
  }
}

// 从槽位读取
function loadFromSlot(slot) {
  try {
    const data = localStorage.getItem(`game_save_${slot}`);
    if (data) {
      game = Game.fromJSON(data);
      updateUI();
      drawGame();
      alert(`已从槽位${slot}读取`);
    } else {
      alert('槽位无数据');
    }
  } catch (e) {
    alert('读取失败');
  }
}

// 事件处理
document.addEventListener('DOMContentLoaded', () => {
  canvas = document.getElementById('gameCanvas');
  ctx = canvas.getContext('2d');

  // 初始化游戏
  initGame('ORBIT-2049');

  // 键盘控制
  document.addEventListener('keydown', (e) => {
    switch (e.key) {
      case 'ArrowUp':
      case 'w':
      case 'W':
        movePlayer(0, -1);
        break;
      case 'ArrowDown':
      case 's':
      case 'S':
        movePlayer(0, 1);
        break;
      case 'ArrowLeft':
      case 'a':
      case 'A':
        movePlayer(-1, 0);
        break;
      case 'ArrowRight':
      case 'd':
      case 'D':
        movePlayer(1, 0);
        break;
      case 'z':
      case 'Z':
        waitAction();
        break;
    }
  });

  // 按钮控制
  document.getElementById('resetBtn').addEventListener('click', () => {
    initGame('ORBIT-2049');
  });

  document.getElementById('loadSeedBtn').addEventListener('click', () => {
    const seed = document.getElementById('seedInput').value;
    if (seed) {
      initGame(seed);
    }
  });

  document.getElementById('saveSlot1').addEventListener('click', () => {
    saveToSlot(1);
  });

  document.getElementById('loadSlot1').addEventListener('click', () => {
    loadFromSlot(1);
  });

  document.getElementById('exportReplay').addEventListener('click', exportReplay);
  document.getElementById('importReplay').addEventListener('click', importReplay);

  // 触屏控制
  document.querySelectorAll('.dir-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const [dx, dy] = e.target.dataset.dir.split(',').map(Number);
      movePlayer(dx, dy);
    });
  });

  document.getElementById('waitBtn').addEventListener('click', waitAction);

  // 绘制初始画面
  drawGame();
});