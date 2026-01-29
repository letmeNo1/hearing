import json
import matplotlib.pyplot as plt
import numpy as np

def plot_dynamic_brightness_curves(json_file_path):
    """
    从JSON文件读取亮度数据，自动识别曲线数量并绘制曲线图
    核心特性：
    1. 不固定线条数，完全根据grid_brightness数组长度自适应
    2. Y轴范围固定为 0 ~ 0.01，聚焦亮度值区间
    3. 完善的异常处理和可视化优化
    """
    # ===================== 1. 读取并验证JSON数据 =====================
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
        
        # 检查数据是否为空
        if not isinstance(data_list, list) or len(data_list) == 0:
            print("错误：JSON文件中没有有效数据（非数组/数组为空）")
            return
        
        # 自动获取曲线数量（从第一条有效数据的grid_brightness长度）
        first_grid_data = data_list[0].get('grid_brightness', [])
        if not isinstance(first_grid_data, list) or len(first_grid_data) == 0:
            print("错误：第一条数据中没有有效的grid_brightness数组")
            return
        grid_count = len(first_grid_data)  # 动态获取曲线数量
        print(f"检测到需要绘制 {grid_count} 条亮度曲线")
        
    except FileNotFoundError:
        print(f"错误：找不到文件 {json_file_path}，请检查路径是否正确")
        return
    except json.JSONDecodeError:
        print("错误：JSON文件格式不正确，请检查文件内容是否符合JSON规范")
        return
    except Exception as e:
        print(f"读取数据时发生未知错误：{str(e)}")
        return

    # ===================== 2. 整理每个grid的亮度数据 =====================
    # 初始化数组：每个元素对应一个grid的所有时间点亮度值
    grid_brightness_all = np.zeros((grid_count, len(data_list)))
    
    # 遍历每条数据，填充亮度值
    for idx, data_point in enumerate(data_list):
        current_brightness = data_point.get('grid_brightness', [])
        # 校验当前数据的grid数量是否与第一条一致（避免数据异常）
        if len(current_brightness) != grid_count:
            print(f"警告：第{idx+1}条数据的grid数量({len(current_brightness)})与第一条({grid_count})不一致，已跳过该条数据")
            continue
        # 将当前数据的亮度值填充到对应位置
        for grid_idx in range(grid_count):
            grid_brightness_all[grid_idx][idx] = current_brightness[grid_idx]

    # ===================== 3. 绘制动态数量的曲线 =====================
    plt.rcParams['font.sans-serif'] = ['SimHei']  # 解决中文显示问题
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(12, 7))  # 设置图表大小
    
    # 生成时间轴（用数据索引代表时间顺序）
    time_axis = np.arange(len(data_list))
    
    # 遍历每个grid，绘制对应的曲线
    for grid_idx in range(grid_count):
        # 为不同曲线分配不同样式（颜色+线型，避免重叠看不清）
        color = plt.cm.tab10(grid_idx % 10)  # 循环使用10种专业配色
        linestyle = '-' if grid_idx % 2 == 0 else '--'  # 交替线型
        plt.plot(
            time_axis, 
            grid_brightness_all[grid_idx],
            label=f'亮度网格 {grid_idx + 1}',
            color=color,
            linestyle=linestyle,
            linewidth=1.2
        )
    
    # ===================== 4. 图表美化与配置（核心修改：固定Y轴范围） =====================
    plt.title('充电盒各网格亮度变化曲线', fontsize=14, fontweight='bold')
    plt.xlabel('数据采集序号（时间顺序）', fontsize=12)
    plt.ylabel('亮度值', fontsize=12)
    plt.grid(True, alpha=0.3)  # 显示网格（透明度0.3，不干扰曲线）
    
    # 核心修改：将Y轴范围固定为 0 到 0.01
    plt.ylim(0, 0.01)
    
    # 智能调整图例位置（避免遮挡曲线）
    if grid_count <= 10:
        plt.legend(loc='best', fontsize=10)
    else:
        # 曲线过多时，将图例放在右侧外部
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        plt.subplots_adjust(right=0.85)  # 预留图例空间
    
    # 显示图表
    plt.tight_layout()  # 自动调整布局
    plt.show()

# ===================== 5. 调用示例 =====================
if __name__ == "__main__":
    # 请将此处替换为你的JSON文件实际路径
    JSON_FILE_PATH = r"C:\Users\swtest\Documents\GitHub\hearing\brightness_log.json"
    plot_dynamic_brightness_curves(JSON_FILE_PATH)