// App 全局逻辑
App({
  onLaunch() {
    // 小程序启动时执行
    console.log('省活攻略 启动')
    // 从本地存储恢复 token
    const token = wx.getStorageSync('token')
    const userInfo = wx.getStorageSync('userInfo')
    if (token) {
      this.globalData.token = token
      this.globalData.userInfo = userInfo || null
    }
  },

  // 全局数据
  globalData: {
    baseUrl: 'http://localhost:8000',  // 后端 API 地址
    token: '',                          // 用户登录 token
    userInfo: null                      // 用户信息
  }
})