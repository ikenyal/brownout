# Brownout — PLAN

ハッカソン: Strands SDK: Workshop to Ship（AWS Builder Center）
締切: 11/4 23:59 PT → **安全側 11/5(木) 15:59 JST**（11/5 正午までに提出完了を目標）
分野: Climate resilience

## コンセプト

普段はゴテゴテにリッチな自治体サイトが、警戒レベルが上がるごとに段階的に身を削り、
レベル5では「最初の1往復（約14KB）」で必要な情報が全部届く1枚になる。
削るだけでなく「何を残すか」をエージェントが判断し、別のエージェントが必須情報の欠落を検証する。

名前の由来: brownout（システムを完全停止させず、機能を落として生き延びる運用）

## 題材（すべて自作。第三者のサイト・文章は使わない）

- 架空の町「七色町（Nanairo Town, fictional）」の公式サイト
- 画像・動画はコードで自作。フォントは OFL ライセンスのもののみ使い、クレジットを併記
- 警戒レベルの区分（1〜5）は日本の公的な枠組みに合わせる。気象庁データ連携はおまけ（利用条件の確認後）

## モード（容量上限は仮。計測で調整する）

| 警戒レベル | モード | 1ページ上限（gzip後の転送量） |
|---|---|---|
| 1〜2 | full（ゴテゴテ） | なし |
| 3 | light | 500KB |
| 4 | lite | 50KB |
| 5 | survival | 14KB |

## 構成（案）

```
警戒レベル変更イベント（擬似 / EventBridge）
  → Brownout エージェント（Strands、AgentCore Runtime 上）
       ├─ Curator  : 災害種別とレベルに応じて、町の情報源（content/）から残す情報を選ぶ
       ├─ Writer   : そのレベルの上限内で HTML を書き起こす
       ├─ Budget   : gzip 後のバイト数をコードで検査（超えたら差し戻し）
       └─ Verifier : レベルごとの必須チェックリストで欠落を検査（不合格なら差し戻し）
  → S3（/level-N/ に配置）
  → CloudFront KeyValueStore の「現在モード」を書き換え
  → CloudFront Function がリクエストを /level-N/ に振り分け（無効化不要で即時切替）
```

- 情報の正本は `content/`（避難所・連絡先・お知らせ等の構造化データ）。エージェントは事実を作らない
- full 版は人間（自作）のゴテゴテサイト。light 以下をエージェントが生成する

## 計測（社会的インパクトの根拠）

- ページの重さ（gzip 転送量）: full vs 各モード
- 低速回線での表示完了時間: Playwright のネットワーク制限（2G/3G 相当）
- 必須情報の残存率: レベル×災害種別のチェックリスト
- 比較対象（ベースライン）: 「機械的に画像・JSを剥がしただけ」の版
- 切替時間: イベント発生 → 新モード配信まで

## 日程

| 日 | 作業 |
|---|---|
| 10/31(土) | ワークショップ修了（Kento）／雛形・七色町の情報源・ゴテゴテ版サイト |
| 11/1(日) | エージェント（Curator/Writer/Budget/Verifier）とローカル評価 |
| 11/2(月) | ベースライン比較・計測スクリプト |
| 11/3(火) | AWS デプロイ（AgentCore Runtime、S3、CloudFront KVS/Function、EventBridge） |
| 11/4(水) | 記事・デモ動画（Polly ナレーション） |
| 11/5(木) 午前 | Public 化・提出 |

## 運用メモ

- リポジトリは ikenyal/brownout（Private で作成、提出直前に Public 化）。ライセンス Apache-2.0
- AWS は brightflow-sandbox-ikeda（us-east-1）
- 動画は @ikenyal、ナレーションは Amazon Polly
