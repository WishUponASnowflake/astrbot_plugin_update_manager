import traceback
from pathlib import Path
from datetime import datetime  # 供调试模式实用

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig

# 导入 APScheduler 库，用于定时任务
from apscheduler.schedulers.asyncio import AsyncIOScheduler

try:
    from astrbot.cli.commands.cmd_plug import (
        build_plug_list,  # 用于获取所有插件信息
        PluginStatus,
    )

    logger.info("成功导入 AstrBot 内部插件管理辅助函数和 PluginManager。")
except ImportError as e:
    logger.error(f"警告：无法导入 AstrBot 内部依赖模块：{e}")
    build_plug_list = None
    PluginStatus = None


@register(
    "astrbot_plugin_update_manager",
    "bushikq",
    "一个用于一键更新和管理所有AstrBot插件的工具，支持定时检查",
    "1.0.2",
)
class PluginUpdateManager(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.interval_hours = self.config.get("interval_hours", 24)
        # self.proxy_address = self.context.get_config()["http_proxy"]代理地址
        self.proxy_address = self.config.get("github_proxy", None)
        self.test_mode = self.config.get("test_mode", False)

        if self.proxy_address:
            logger.info(f"使用代理：{self.proxy_address}")
        else:
            logger.info("未设置代理。")

        if self.interval_hours:
            # 初始化 APScheduler 调度器
            self.scheduler = AsyncIOScheduler()
            # 添加一个定时任务，检查并更新插件
            self.scheduler.add_job(
                self._scheduled_update_check,
                "interval",
                hours=self.interval_hours,
                id="scheduled_plugin_update",
                name="Scheduled Plugin Update Check",
            )
            # 启动调度器
            self.scheduler.start()
            logger.info("插件更新管理器已启动，定时任务已安排。")
        else:
            logger.info("插件更新管理器已启动，但未配置定时任务。")

    async def _scheduled_update_check(self):
        """
        这个方法会被 APScheduler 定时调用，用于检查并更新所有插件。
        """
        logger.info("定时任务：正在检查并更新所有插件...")
        await self._check_and_perform_updates()  # 不需要返回给用户，只记录日志

    async def _check_and_perform_updates(self) -> str:
        """
        返回一个字符串，包含更新的结果摘要。
        """
        # 检查所有必要的依赖是否成功导入
        if not all(
            [
                build_plug_list,
                PluginStatus,
            ]
        ):
            error_msg = "机器人内部依赖功能未加载，无法执行更新。"
            logger.error(f"错误：核心依赖模块未加载，{error_msg}")
            return error_msg

        plug_path = Path(__file__).resolve().parent.parent
        logger.info(f"插件目录：{plug_path}")
        if not plug_path.is_dir():
            error_msg = f"未找到插件目录 {plug_path}，无法执行更新。"
            logger.error(f"错误：未找到插件目录 {plug_path}。")
            return error_msg

        update_summary_messages = []
        failed_plugins = []
        successed_plugins = []

        try:
            all_plugins_info = build_plug_list(plug_path)
            if self.test_mode:  # 调试模式
                with open(
                    Path(__file__).resolve().parent / "test.md", "w", encoding="utf-8"
                ) as f:
                    f.write(f"于{datetime.now()}记录\n {all_plugins_info}")
                    logger.info("调试模式：已生成测试文件 test.md。")
            need_update_plugins = [
                p
                for p in all_plugins_info
                if p.get("status") == PluginStatus.NEED_UPDATE
            ]

            if not need_update_plugins:
                message = "目前没有发现需要更新的插件。"
                logger.info(f"{message}")
                return message

            # 提取需要更新插件的名称列表，用于日志输出
            plugin_names_to_update = [
                p.get("name") for p in need_update_plugins if p.get("name")
            ]
            logger.info(
                f"发现 {len(need_update_plugins)} 个需要更新的插件：{plugin_names_to_update}。"
            )
            update_summary_messages.append(
                f"发现 {len(need_update_plugins)} 个插件需要更新。"
            )

            # 遍历并逐个更新插件
            for plugin_item in need_update_plugins:
                plugin_name_to_update = plugin_item.get("name")
                if not plugin_name_to_update:
                    logger.warning(f"发现一个缺少 'name' 的插件信息: {plugin_item}")
                    continue

                try:
                    logger.info(f"正在更新插件：{plugin_name_to_update}...")
                    await self.context._star_manager.update_plugin(
                        plugin_name=plugin_name_to_update,
                        proxy=self.proxy_address,
                    )
                    # await self.context._star_manager.reload(specified_plugin_name=plugin_name_to_update)实测会自动重载插件，无需手动重新加载
                    logger.info(f"插件 {plugin_name_to_update} 更新并已自动重新加载。")
                    successed_plugins.append(plugin_name_to_update)

                except Exception as e:
                    error_msg = f"更新插件 {plugin_name_to_update} 失败: {str(e)}"
                    failed_plugins.append(plugin_name_to_update)
                    logger.error(f"{error_msg}\n{traceback.format_exc()}")

            # 构建最终的回复消息
            final_reply_to_user = "\n".join(update_summary_messages)
            if failed_plugins:
                final_reply_to_user += f"\n\n注意：部分插件更新失败：{', '.join(failed_plugins)}。请检查机器人日志获取详细信息。"
            final_reply_to_user += (
                f"\n成功更新 {len(successed_plugins)} 个插件。\n{successed_plugins}"
            )
            return final_reply_to_user

        except Exception as e:
            error_msg = f"插件更新流程中发生意外错误: {traceback.format_exc()}"
            logger.error(f"{error_msg}")
            return f"插件更新流程异常终止: {e}。请检查机器人日志。"

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("更新所有插件", alias={"updateallplugins", "更新全部插件"})
    async def update_all_plugins_command(self, event: AstrMessageEvent):
        """
        当用户发送 "更新所有插件" 命令时，触发检查并更新所有需要更新的插件。
        """
        logger.info("收到用户命令 '更新所有插件'。")
        yield event.plain_result("正在检查并更新所有插件，请稍候...")

        # 调用核心更新逻辑，并将结果返回给用户
        result_message = await self._check_and_perform_updates()
        yield event.plain_result(result_message)

    async def terminate(self):
        """
        插件终止时（例如：插件被禁用或机器人关闭），关闭 APScheduler 定时任务。
        """
        if self.scheduler.running:
            self.scheduler.shutdown()  # 关闭调度器
            logger.info("定时任务调度器已关闭。")
