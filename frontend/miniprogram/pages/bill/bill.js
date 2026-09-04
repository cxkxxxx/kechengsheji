// 账单页逻辑
const { request } = require('../../utils/request')
const { currentMonth } = require('../../utils/util')

Page({
  data: { bills: [], summary: {} },

  onLoad() { this.loadData() },

  async loadData() {
    const month = currentMonth()
    try {
      const [bills, summary] = await Promise.all([
        request('/bills?month=' + month),
        request('/bills/summary?month=' + month)
      ])
      this.setData({ bills: bills || [], summary: summary || {} })
    } catch (e) { console.error(e) }
  },

  addBill() {
    // TODO: 弹出录入弹窗
    wx.showToast({ title: '记一笔功能开发中', icon: 'none' })
  }
})
