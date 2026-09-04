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

module.exports = { formatDate, formatMoney, currentMonth }
