// 导入游戏引擎
// 在浏览器环境中，Game 类由 engine.cjs 提供

// 游戏状态
let game = null;
let canvas = null;
let ctx = null;
let tile_size = 32;
let view_radius = 3;
let replayActions = []; // 存储回放动作

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
  
  // 记录动作用于回放
  if (success) {
    replayActions.push({ type: 'move', dx, dy });
  }
  
  return success;
}

// 等待动作
function waitAction() {
  if (!game || game.status !== 'playing') return false;

  game.wait();
  updateUI();
  drawGame();
  
  // 记录动作用于回放
  replayActions.push({ type: 'wait' });
  
  return true;
}

// 导出回放
function exportReplay() {
  if (!game) return;
  
  const replayData = {
    seed: game.seed,
    actions: replayActions
  };
  
  const json = JSON.stringify(replayData);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `replay_${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// 导入回放
function importReplay() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  
  input.onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target.result);
        
        // 重新生成游戏并应用回放
        game = new Game({ seed: data.seed });
        replayActions = data.actions || [];
        
        // 应用所有动作
        for (const action of replayActions) {
          if (action.type === 'move') {
            game.move(action.dx, action.dy);
          } else if (action.type === 'wait') {
            game.wait();
          }
        }
        
        updateUI();
        drawGame();
        alert('回放加载成功');
      } catch (error) {
        alert('回放文件格式错误或损坏');
        console.error(error);
      }
    };
    
    reader.readAsText(file);
  };
  
  input.click();
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

// 冲刺动作
function dash(dx, dy) {
  if (!game || game.status !== 'playing') return false;
  
  // 检查是否可以冲刺（能量足够）
  if (game.player.energy < 1) return false;
  
  // 第一格移动
  const newX = game.player.x + dx;
  const newY = game.player.y + dy;
  
  // 检查边界和墙
  if (newX < 0 || newX >= game.width || newY < 0 || newY >= game.height ||
      game.grid[newY][newX] === TILE_TYPES.WALL) {
    return false; // 第一格受阻，完全不行动
  }
  
  // 移动到第一格并消耗能量
  game.player.x = newX;
  game.player.y = newY;
  game.player.energy--;
  
  // 检查是否收集芯片
  const chipIndex = game.chips.findIndex(chip => chip.x === newX && chip.y === newY);
  if (chipIndex !== -1) {
    game.chips.splice(chipIndex, 1);
    game.collected++;
  }
  
  // 检查是否获得补给
  if (game.grid[newY][newX] === TILE_TYPES.SUPPLY) {
    game.player.energy += 5;
    game.grid[newY][newX] = TILE_TYPES.EMPTY;
  }
  
  // 检查是否到达出口
  if (game.grid[newY][newX] === TILE_TYPES.EXIT) {
    if (game.collected >= 3) {
      game.status = 'won';
    }
  }
  
  // 第二格移动（如果第一格有效）
  const secondX = game.player.x + dx;
  const secondY = game.player.y + dy;
  
  if (secondX >= 0 && secondX < game.width && secondY >= 0 && secondY < game.height &&
      game.grid[secondY][secondX] !== TILE_TYPES.WALL) {
    // 移动到第二格
    game.player.x = secondX;
    game.player.y = secondY;
    
    // 检查是否收集芯片（第二格）
    const chipIndex2 = game.chips.findIndex(chip => chip.x === secondX && chip.y === secondY);
    if (chipIndex2 !== -1) {
      game.chips.splice(chipIndex2, 1);
      game.collected++;
    }
    
    // 检查是否获得补给（第二格）
    if (game.grid[secondY][secondX] === TILE_TYPES.SUPPLY) {
      game.player.energy += 5;
      game.grid[secondY][secondX] = TILE_TYPES.EMPTY;
    }
    
    // 检查是否到达出口（第二格）
    if (game.grid[secondY][secondX] === TILE_TYPES.EXIT) {
      if (game.collected >= 3) {
        game.status = 'won';
      }
    }
    
    // 耗能1
    game.player.energy--;
  } else {
    // 第二格受阻，只在第一格停下并耗能1
    // 已经在第一格，只需耗能1
  }
  
  // 敌人行动
  game._enemyAction();
  
  // 增加回合数（冲刺只推进一个回合）
  game.turn++;
  
  return true;
}

// 键盘控制处理
function handleKeyDown(e) {
  switch (e.key) {
    case 'ArrowUp':
    case 'w':
    case 'W':
      if (e.shiftKey) {
        dash(0, -1);
      } else {
        movePlayer(0, -1);
      }
      break;
    case 'ArrowDown':
    case 's':
    case 'S':
      if (e.shiftKey) {
        dash(0, 1);
      } else {
        movePlayer(0, 1);
      }
      break;
    case 'ArrowLeft':
    case 'a':
    case 'A':
      if (e.shiftKey) {
        dash(-1, 0);
      } else {
        movePlayer(-1, 0);
      }
      break;
    case 'ArrowRight':
    case 'd':
    case 'D':
      if (e.shiftKey) {
        dash(1, 0);
      } else {
        movePlayer(1, 0);
      }
      break;
    case 'z':
    case 'Z':
      waitAction();
      break;
  }
}

// 事件处理
document.addEventListener('DOMContentLoaded', () => {
  canvas = document.getElementById('gameCanvas');
  ctx = canvas.getContext('2d');

  // 初始化游戏
  initGame('ORBIT-2049');

  // 键盘控制
  document.addEventListener('keydown', handleKeyDown);

  // 按钮控制
  document.getElementById('resetBtn').addEventListener('click', () => {
    replayActions = [];
    initGame('ORBIT-2049');
  });

  document.getElementById('loadSeedBtn').addEventListener('click', () => {
    const seed = document.getElementById('seedInput').value;
    if (seed) {
      replayActions = [];
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