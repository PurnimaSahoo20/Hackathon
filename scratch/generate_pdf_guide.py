import matplotlib.pyplot as plt

def create_tshirt_size_guide_pdf(filename):
    # Set figure size (A4 ratio approx 8.27 x 11.69 inches)
    fig, ax = plt.subplots(figsize=(8.5, 11))
    ax.axis('off')

    # Color scheme (matching theme: deep slate & orange accent)
    accent_color = '#ea580c'
    header_bg = '#fff7ed'
    table_header_bg = '#ea580c'
    text_color = '#1e293b'
    border_color = '#fed7aa'

    # Title Banner
    fig.patches.extend([
        plt.Rectangle((0.05, 0.88), 0.9, 0.08, fill=True, color='#ea580c', transform=fig.transFigure, figure=fig, zorder=1),
    ])
    fig.text(0.5, 0.93, "HACKNEXUS — T-SHIRT SIZE GUIDELINE", fontsize=18, fontweight='bold', color='white', ha='center', va='center')
    fig.text(0.5, 0.90, "Official Size Measurement Chart for Participants & Team Members", fontsize=11, color='#ffedd5', ha='center', va='center')

    # Description Section
    fig.text(0.08, 0.84, "How to Choose Your Size:", fontsize=13, fontweight='bold', color=text_color)
    desc_text = (
        "• Please refer to the size chart below before selecting your T-shirt size in the form.\n"
        "• Measurements are provided in inches and apply to regular-fit unisex T-shirts.\n"
        "• If you prefer a relaxed or looser fit, we recommend choosing one size larger."
    )
    fig.text(0.08, 0.77, desc_text, fontsize=10.5, color='#475569', linespacing=1.6)

    # Size Chart Table Data
    columns = ["Size", "Chest (Inches)", "Length (Inches)", "Shoulder (Inches)", "Recommended Body Fit"]
    data = [
        ["S (Small)", "36\"", "26\"", "16.5\"", "34\" - 36\""],
        ["M (Medium)", "38\"", "27\"", "17.5\"", "37\" - 39\""],
        ["L (Large)", "40\"", "28\"", "18.5\"", "40\" - 42\""],
        ["XL (Extra Large)", "42\"", "29\"", "19.5\"", "43\" - 45\""],
        ["XXL (Double XL)", "44\"", "30\"", "20.5\"", "46\" - 48\""]
    ]

    # Create Table
    table_ax = fig.add_axes([0.08, 0.42, 0.84, 0.30])
    table_ax.axis('off')
    
    table = table_ax.table(
        cellText=data,
        colLabels=columns,
        cellLoc='center',
        loc='center'
    )
    table.scale(1, 2.2)
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    # Style Table Cells
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor(table_header_bg)
            cell.set_text_props(color='white', weight='bold', fontsize=10.5)
            cell.set_edgecolor('#c2410c')
        else:
            bg_color = '#fff' if row % 2 == 1 else '#f8fafc'
            cell.set_facecolor(bg_color)
            cell.set_text_props(color=text_color, fontsize=10)
            cell.set_edgecolor('#e2e8f0')

    # Measurement Tips & Visual Guide Box
    fig.patches.extend([
        plt.Rectangle((0.08, 0.15), 0.84, 0.22, fill=True, color='#f8fafc', edgecolor='#cbd5e1', linewidth=1.5, transform=fig.transFigure, figure=fig),
    ])
    fig.text(0.11, 0.33, "Tips for Accurate Measurement:", fontsize=12, fontweight='bold', color=accent_color)
    
    tips_text = (
        "1. CHEST: Measure around the fullest part of your chest, keeping the tape horizontally level.\n"
        "2. LENGTH: Measure from the highest point of the shoulder seam down to the bottom hem of the shirt.\n"
        "3. SHOULDER: Measure across the back from shoulder point to shoulder point.\n\n"
        "Note: T-shirt exchanges during the event are subject to stock availability."
    )
    fig.text(0.11, 0.18, tips_text, fontsize=9.5, color='#334155', linespacing=1.6)

    # Footer
    fig.text(0.5, 0.06, "HackNexus Event Management System • T-Shirt Size Guideline Document", fontsize=9, color='#94a3b8', ha='center')

    plt.tight_layout()
    plt.savefig(filename, format='pdf', bbox_inches='tight', dpi=300)
    plt.close()
    print(f"PDF generated successfully at: {filename}")

if __name__ == "__main__":
    create_tshirt_size_guide_pdf("d:/OKCL/Bput-Hackathon/Bput-Hackathon/media/tshirt_size_guidelines.pdf")
    create_tshirt_size_guide_pdf("d:/OKCL/Bput-Hackathon/Bput-Hackathon/staticfiles/tshirt_size_guidelines.pdf")
