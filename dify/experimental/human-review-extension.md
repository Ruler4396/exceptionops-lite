# Experimental Dify Human Input Path

v1 的主路径把人工审核放在自有案例详情页中，以保证案例状态、审计日志和 review 历史都在自有后端统一管理。

如果需要额外展示 Dify Human Input，可以在主工作流后面插入：

1. `If/Else`: `needs_human_review == true`
2. `Human Input`: 让 reviewer 选择 `approve / reject / request_more_info`
3. `Template` or `Code`: 整理人工输入结果
4. `HTTP Request`: 回写后端 `/api/cases/{case_id}/review`

不建议把它作为 v1 的唯一 review 入口，因为那会造成：

- 状态源分裂
- 审计留痕分散
- 演示路径跳出自有界面

