"""
文件转换模块 - 将Word/Excel/图片等转换为PDF
使用 win32com 调用本地 WPS/Office 实现高保真转换
增加加密文件检测，兼容旧版 olefile
"""

import os
import shutil
import win32com.client


def _is_pdf_encrypted(file_path):
    """检测PDF是否加密"""
    try:
        import fitz
        doc = fitz.open(file_path)
        encrypted = doc.is_encrypted
        doc.close()
        return encrypted
    except Exception:
        return True


def _is_office_encrypted(file_path):
    """
    检测Office文件是否加密
    兼容新旧版本的 olefile
    """
    try:
        import olefile
        # 新版 olefile (0.47+) 有 is_encrypted 函数
        if hasattr(olefile, 'is_encrypted'):
            return olefile.is_encrypted(file_path)
        else:
            # 旧版 olefile：通过 OleFileIO 打开并检查
            with olefile.OleFileIO(file_path) as ole:
                return ole.is_encrypted
    except Exception:
        # 任何检测失败，默认返回 False（未加密），继续转换
        return False


def convert_to_pdf(input_path: str, output_path: str) -> bool:
    """
    根据文件扩展名自动选择转换方式，将文件转为PDF
    返回 True 表示成功，False 表示失败
    """
    ext = os.path.splitext(input_path)[1].lower()
    try:
        # ----- 加密检测（避免弹窗） -----
        if ext == '.pdf':
            if _is_pdf_encrypted(input_path):
                raise ValueError("PDF文件已加密，无法处理")
        elif ext in {'.doc', '.docx', '.xls', '.xlsx'}:
            if _is_office_encrypted(input_path):
                raise ValueError("Office文件已加密，无法处理")
        # --------------------------------
        
        if ext in {'.doc', '.docx'}:
            return _convert_word_to_pdf(input_path, output_path)
        elif ext in {'.xls', '.xlsx'}:
            return _convert_excel_to_pdf(input_path, output_path)
        elif ext in {'.pdf'}:
            shutil.copy2(input_path, output_path)
            return True
        elif ext in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}:
            return _convert_image_to_pdf(input_path, output_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    except Exception as e:
        import traceback
        print(f"转换失败 [{input_path}]: {str(e)}")
        traceback.print_exc()
        return False


def _convert_word_to_pdf(input_path: str, output_path: str) -> bool:
    try:
        # 尝试 WPS 文字
        try:
            app = win32com.client.Dispatch("kwps.Application")
        except:
            # 回退到 Microsoft Word
            app = win32com.client.Dispatch("Word.Application")
        app.Visible = False
        doc = app.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=17)  # wdFormatPDF
        doc.Close()
        app.Quit()
        return True
    except Exception as e:
        raise RuntimeError(f"Word 转换失败: {str(e)}")


def _convert_excel_to_pdf(input_path: str, output_path: str) -> bool:
    try:
        # 尝试 WPS 表格
        try:
            app = win32com.client.Dispatch("ket.Application")
        except:
            try:
                app = win32com.client.Dispatch("et.Application")
            except:
                app = win32com.client.Dispatch("Excel.Application")
        app.Visible = False
        wb = app.Workbooks.Open(input_path)
        wb.SaveAs(output_path, FileFormat=103)  # xlTypePDF
        wb.Close()
        app.Quit()
        return True
    except Exception as e:
        raise RuntimeError(f"Excel 转换失败: {str(e)}")


def _convert_image_to_pdf(input_path: str, output_path: str) -> bool:
    try:
        import img2pdf
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert(input_path))
        return True
    except Exception as e:
        raise RuntimeError(f"图片转换失败: {str(e)}")