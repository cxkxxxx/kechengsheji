// 月度消费日历（热力图）：首页和账单页共用一套，数据聚合规则只在这一个文件里。
// 颜色分档按「当天支出 ÷ 当月峰值」的比例：>66% l4、>33% l3、>12% l2、其余 l1、无消费 l0。
Component({
  properties: {
    month: { type: String, value: '' },        // YYYY-MM
    bills: { type: Array, value: [] },          // 该月账单 [{bill_date, amount}]
    title: { type: String, value: '消费日历' }   // 卡片标题（不带月份前缀）
  },

  data: {
    cells: [],
    max: '—',
    monthLabel: '',
    picked: false,
    pickedLabel: '',
    pickedAmount: '',
    pickedCount: 0
  },

  observers: {
    'month, bills': function () { this.rebuild() }
  },

  methods: {
    rebuild() {
      const month = this.data.month
      if (!month) return
      const bills = this.data.bills || []
      const byDay = {}
      bills.forEach(b => {
        const d = parseInt(String(b.bill_date || '').slice(8, 10), 10)
        if (!d) return
        byDay[d] = byDay[d] || { amount: 0, count: 0 }
        byDay[d].amount += parseFloat(b.amount) || 0
        byDay[d].count += 1
      })
      const y = parseInt(month.slice(0, 4), 10)
      const m = parseInt(month.slice(5, 7), 10)
      const dim = new Date(y, m, 0).getDate()
      const lead = new Date(y, m - 1, 1).getDay()     // 当月 1 号前面空几格（周日开头）
      const now = new Date()
      const isNow = month === (now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0'))
      const today = isNow ? now.getDate() : 0
      const vals = Object.keys(byDay).map(k => byDay[k].amount)
      const max = vals.length ? Math.max.apply(null, vals) : 0

      const cells = []
      for (let i = 0; i < lead; i++) cells.push({ key: 'e' + i, day: 0, cls: 'cal-empty' })
      for (let d = 1; d <= dim; d++) {
        const v = byDay[d] ? byDay[d].amount : 0
        let cls = v > 0 ? 'cal-l1' : 'cal-l0'
        if (max > 0 && v > 0) {
          const r = v / max
          cls = r > 0.66 ? 'cal-l4' : r > 0.33 ? 'cal-l3' : r > 0.12 ? 'cal-l2' : 'cal-l1'
        }
        cells.push({
          key: 'd' + d, day: d, cls,
          short: v >= 1000 ? (v / 1000).toFixed(1) + 'k' : (v ? Math.round(v) : ''),
          isToday: d === today
        })
      }
      this.setData({
        cells,
        max: max ? String(Math.round(max * 100) / 100) : '—',
        monthLabel: m + '月',
        picked: false, pickedLabel: '', pickedAmount: '', pickedCount: 0
      })
    },

    onTapDay(e) {
      const d = parseInt(e.currentTarget.dataset.day, 10)
      if (!d) return
      const day = String(d).padStart(2, '0')
      const rows = (this.data.bills || []).filter(b => String(b.bill_date || '').slice(0, 10) === this.data.month + '-' + day)
      const sum = rows.reduce((s, b) => s + (parseFloat(b.amount) || 0), 0)
      const picked = {
        picked: true,
        pickedLabel: this.data.month.slice(5) + '月' + d + '日',
        pickedAmount: String(Math.round(sum * 100) / 100),
        pickedCount: rows.length
      }
      this.setData(picked)
      // 把当天明细抛给页面：首页弹当天清单，账单页想滚动到明细也用得上
      this.triggerEvent('daypick', { day: d, date: this.data.month + '-' + day, count: rows.length })
    }
  }
})
