"""Isolated synthetic editorial response for renderer/weekly tests; never production."""
def generated(article):
    return dict(ready=True, facts=[dict(text='NVIDIA 提到把素材、物理模擬與渲染串成模擬測試流程。', evidence='synthetic renderer fixture')],
                background='物理模擬以數學近似真實系統，需要用量測校準。',
                impact='模擬工具可能改變工程師建立與驗證場景的流程。',
                attention='檢查素材格式、物理誤差與工具版本能否重現結果。',
                outlook='觀察是否公開可重跑案例與實體量測對照。',
                opening='讓電腦先演練一遍，真的能代替實體測試嗎？我們來拆開模擬和真實世界的差距。',
                questions=['物理結果能否重現？'],gaps=['需要公開工具文件與測試案例。']),None
