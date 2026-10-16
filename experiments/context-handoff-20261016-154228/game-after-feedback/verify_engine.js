// 验证引擎行为的脚本
const { Game } = require('./engine.cjs');

console.log('=== 游戏引擎验证 ===');

// 测试1: 种子复现
console.log('\n1. 测试种子复现:');
const game1 = new Game({ seed: 'ORBIT-2049' });
const game2 = new Game({ seed: 'ORBIT-2049' });
console.log('  玩家位置一致:', game1.player.x === game2.player.x && game1.player.y === game2.player.y);
console.log('  芯片位置一致:', JSON.stringify(game1.chips) === JSON.stringify(game2.chips));

// 测试2: 地图生成
console.log('\n2. 测试地图生成:');
console.log('  玩家起始位置:', game1.player.x, game1.player.y);
console.log('  芯片数量:', game1.chips.length);
console.log('  出口位置:', game1.grid[0].indexOf(5) !== -1 ? '存在' : '不存在');

// 测试3: 移动逻辑
console.log('\n3. 测试移动逻辑:');
console.log('  初始回合数:', game1.turn);
const moveResult = game1.move(1, 0); // 向右移动
console.log('  移动结果:', moveResult);
console.log('  移动后回合数:', game1.turn);
console.log('  能量消耗:', game1.player.energy === 11);

// 测试4: 无效移动测试
console.log('\n4. 测试无效移动:');
const initialTurn = game1.turn;
game1.move(0, 0); // 无效移动
console.log('  无效移动后回合数:', game1.turn);
console.log('  回合未推进:', game1.turn === initialTurn);

// 测试5: 序列化
console.log('\n5. 测试序列化:');
const serialized = game1.serialize();
const restored = Game.fromJSON(serialized);
console.log('  序列化还原成功:', restored.player.x === game1.player.x && restored.player.y === game1.player.y);

console.log('\n=== 验证完成 ===');