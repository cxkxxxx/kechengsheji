// 通用工具函数

// 格式化日期 YYYY-MM-DD
function formatDate(date) {
  const d = new Date(date)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return y + '-' + m + '-' + day
}

// 格式化金额（保留2位小数）
function formatMoney(num) {
  return parseFloat(num || 0).toFixed(2)
}

// 获取当前月份 YYYY-MM
function currentMonth() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}

// 图片地址：库里存的是 /static/xxx.jpg 相对路径，<image> 组件必须拿到绝对地址才加载得动。
// 帖子和攻略共用，所以收在这里而不是各页面各写一遍。
function fullUrl(u) {
  if (!u) return ''
  if (u.indexOf('http') === 0) return u
  const app = getApp()
  const base = (app && app.globalData && app.globalData.baseUrl) || 'http://localhost:8000'
  return base + u
}

// 九宫格：给图片数组补上绝对地址和列数类名（app.wxss 里的 .imgs-1 … .imgs-9）
function imageGrid(urls, max) {
  const list = (urls || []).filter(Boolean).slice(0, max || 9)
  return { list: list.map(fullUrl), cls: 'imgs imgs-' + Math.min(list.length, 9), n: list.length }
}

module.exports = { formatDate, formatMoney, currentMonth, fullUrl, imageGrid }
