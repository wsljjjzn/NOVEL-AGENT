"""
models.character — 角色的一等公民模型。

支持逐章追踪：角色不是静态描述，而是随着剧情演变的状态机。
每个角色记录 base_profile（不变特质）和 chapter_states（逐章演变）。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RelationshipState(BaseModel):
    """角色间关系（支持变化追踪）。"""
    target: str = Field(description="对方角色名")
    status: str = Field(default="未知", description="当前关系：友好/敌对/暗恋/恐惧/依赖/...")
    history: list[dict] = Field(default_factory=list, description="[(章号, 事件, 变化)]")


class ChapterState(BaseModel):
    """角色在某一章的状态快照。"""
    chapter_index: int = Field(description="章号")
    mood: str = Field(default="", description="当前情绪：恐惧/愤怒/喜悦/悲伤/...")
    motivation: str = Field(default="", description="当前驱动目标：本章想要什么")
    behavior_shift: str = Field(default="", description="行为变化：相比上一章有什么不同")
    trigger: str = Field(default="", description="触发变化的事件")
    key_action: str = Field(default="", description="本章做出的关键行动/决定")
    relationship_changes: list[dict] = Field(default_factory=list,
        description="[(对方角色, 变化描述, 新状态)]")
    new_info_learned: str = Field(default="", description="本章获得了什么新信息")
    inner_conflict: str = Field(default="", description="内心矛盾")


class DialogueStyle(BaseModel):
    """角色的语言风格特征。"""
    sentence_pattern: str = Field(default="", description="句式特征：短句多/长句多/反问多")
    catchphrases: list[str] = Field(default_factory=list, description="口头禅/标志性用语")
    address_others: dict[str, str] = Field(default_factory=dict,
        description="{对方角色: 称呼方式}")
    tone_tendency: str = Field(default="", description="语气倾向：冷淡/热情/讽刺/恭敬")


class Character(BaseModel):
    """角色 — 故事中的一等公民。"""
    character_id: str = Field(description="唯一标识")
    name: str = Field(description="角色名")
    aliases: list[str] = Field(default_factory=list, description="别名/昵称/曾用名")
    source_file: str = Field(default="", description="来源素材文件")

    # 不变特质
    base_profile: dict = Field(default_factory=dict,
        description="{年龄, 身份, 外貌, 核心欲望, 核心恐惧}")
    personality: dict = Field(default_factory=dict,
        description="{MBTI/大五人格, 说话方式, 习惯动作, 优点, 缺点}")

    # 逐章演变（核心）
    chapter_states: list[ChapterState] = Field(default_factory=list)

    # 关系网
    relationship_map: dict[str, str] = Field(default_factory=dict,
        description="{对方角色: 当前关系状态概要}")
    relationship_details: list[RelationshipState] = Field(default_factory=list)

    # 语言风格
    dialogue_style: DialogueStyle = Field(default_factory=DialogueStyle)

    # 弧线总结
    arc_summary: str = Field(default="", description="从开头到结局的角色弧线总结")

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def get_state_at_chapter(self, chapter_index: int) -> Optional[ChapterState]:
        """获取角色在指定章的状态（<=chapter_index 的最新一条）。"""
        valid = [s for s in self.chapter_states if s.chapter_index <= chapter_index]
        if not valid:
            return None
        return max(valid, key=lambda s: s.chapter_index)

    def add_chapter_state(self, state: ChapterState):
        """追加一章的状态。"""
        # 如果该章已存在则替换，否则追加
        for i, s in enumerate(self.chapter_states):
            if s.chapter_index == state.chapter_index:
                self.chapter_states[i] = state
                return
        self.chapter_states.append(state)

    def get_relationship(self, target: str) -> Optional[RelationshipState]:
        """获取与指定角色的关系详情。"""
        for r in self.relationship_details:
            if r.target == target:
                return r
        return None

    def get_mood_trend(self) -> list[dict]:
        """获取情绪变化趋势。"""
        return [{"chapter": s.chapter_index, "mood": s.mood}
                for s in sorted(self.chapter_states, key=lambda x: x.chapter_index)]
