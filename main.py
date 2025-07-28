import traceback  # 导入 traceback 用于打印详细错误信息
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

try:
    from astrbot.cli.commands.cmd_plug import (
        build_plug_list,  # 用于获取所有插件信息
        _get_data_path,  # 用于获取数据目录，进而获得插件目录
        PluginStatus,
    )

    logger.info("成功导入 AstrBot 内部插件管理辅助函数。")
except ImportError as e:
    logger.error(f"警告：无法导入 AstrBot 内部插件管理辅助函数{e}")
    build_plug_list = None  # 用来标志插件管理辅助函数是否导入成功，在后续代码中进行判断


@register(
    "astrbot_plugin_update_manager",
    "bushikq",
    "一个用于一键更新所有astrbot插件的插件",
    "1.0.0",
)
class UpdaterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("更新所有插件", alias="updateallplugins")
    async def update_all_plugins_command(self, event: AstrMessageEvent):
        """
        当用户发送 "更新所有插件" 命令时，检查并更新所有需要更新的插件。
        """
        logger.info("收到 '更新所有插件' 命令，正在检查并更新所有插件，请稍候...")
        yield event.plain_result("正在检查并更新所有插件，请稍候...")

        # 检查依赖函数是否成功导入
        if not build_plug_list:
            yield event.plain_result(
                "机器人内部依赖功能未加载，无法执行更新。请检查机器人日志以获取更多信息。"
            )
            logger.error("错误：核心辅助函数未加载，无法执行更新。")
            return

        data_path = _get_data_path()  # 应为AstrBot\data
        logger.info(f"data_path: {data_path}")
        plug_path = data_path / "plugins"
        if not plug_path.is_dir():
            yield event.plain_result(f"未找到插件目录 {plug_path}，无法执行更新。")
            logger.error(f"错误：未找到插件目录 {plug_path}。")
            return

        update_summary_messages = []
        failed_plugins = []

        try:
            all_plugins_info = build_plug_list(plug_path)  # 获取所有插件的列表和状态
            need_update_plugins = [
                p
                for p in all_plugins_info
                if p.get("status") == PluginStatus.NEED_UPDATE
            ]

            if not need_update_plugins:
                yield event.plain_result("目前没有发现需要更新的插件。")
                return
            logger.info(
                f"发现 {len(need_update_plugins)} 个需要更新的插件，为{need_update_plugins}。"
            )
            update_summary_messages.append(
                f"发现 {len(need_update_plugins)} 个插件需要更新。"
            )

            # 遍历并逐个更新插件
            for plugin_item in need_update_plugins:
                plugin_name_to_update = plugin_item.get("name")
                if not plugin_name_to_update:
                    logger.warning(f"发现一个缺少 'name' 的插件信息: {plugin_item}")
                    failed_plugins.append(plugin_item)
                    continue

                try:
                    logger.info(f"正在更新插件：{plugin_name_to_update}...")
                    await self.context._star_manager.update_plugin(
                        plugin_name=plugin_name_to_update
                    )
                    # await self.context._star_manager.reload(specified_plugin_name=plugin_name_to_update)实测会自动重载插件，无需手动重新加载
                    logger.info(f"插件 {plugin_name_to_update} 更新并已自动重新加载。")

                except Exception as e:
                    error_msg = f"更新插件 {plugin_name_to_update} 失败: {str(e)}"
                    update_summary_messages.append(error_msg)
                    failed_plugins.append(plugin_name_to_update)
                    logger.error(f"{error_msg}\n{traceback.format_exc()}")

            final_reply_to_user = "\n".join(update_summary_messages)
            if failed_plugins:
                final_reply_to_user += f"\n\n注意：部分插件更新失败：{', '.join(failed_plugins)}。请检查机器人日志获取详细信息。"
            else:
                success_count = len(need_update_plugins) - len(failed_plugins)
                final_reply_to_user += f"\n\n成功更新 {success_count} 个插件。"

            yield event.plain_result(final_reply_to_user)

        except Exception as e:
            logger.error(f"插件更新流程中发生意外错误: {traceback.format_exc()}")
            yield event.plain_result(f"插件更新流程异常终止: {e}。请检查机器人日志。")
